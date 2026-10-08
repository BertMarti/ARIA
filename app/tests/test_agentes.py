"""Agentes: selección, enrutado, restricciones por rol y herramientas por agente."""
import asyncio

import pytest

from aria import agentes, cerebros, chat, db, tools, usuarios


def correr(gen):
    async def todo():
        return [e async for e in gen]
    return asyncio.run(todo())


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


@pytest.fixture
def sin_nube(monkeypatch):
    llamadas = []

    async def clasif(texto, candidatos):
        llamadas.append((texto, candidatos))
        return None
    monkeypatch.setattr(agentes, "clasificar_con_nube", clasif)
    return llamadas


def test_prefijo():
    assert agentes.separar_prefijo("@finanzas ¿cuánto gasté?") == ("finanzas", "¿cuánto gasté?")
    assert agentes.separar_prefijo("@Redes: ping") == ("redes", "ping")
    assert agentes.separar_prefijo("@desconocido hola") == (None, "@desconocido hola")
    assert agentes.separar_prefijo("hola @finanzas") == (None, "hola @finanzas")


def test_disponibles_por_rol():
    assert {a["id"] for a in agentes.disponibles("admin")} == {"aria", "finanzas", "redes", "seguridad"}
    assert {a["id"] for a in agentes.disponibles("usuario")} == {"aria", "finanzas", "redes"}
    assert not agentes.permitido("seguridad", "usuario") and agentes.permitido("seguridad", "admin")
    assert not agentes.permitido("inventado", "admin")


@pytest.mark.parametrize("texto,esperado", [
    ("¿Cuánto he gastado este mes en el supermercado?", "finanzas"),
    ("Pon un presupuesto de 200 euros para ocio", "finanzas"),
    ("¿Qué latencia tengo con el router?", "redes"),
    ("Haz un test de velocidad", "redes"),
    ("Escanea los puertos y dime las vulnerabilidades", "seguridad"),
    ("Cuéntame un chiste", "aria"),
    ("¿Qué hora es?", "aria"),
])
def test_enrutado_por_palabras(texto, esperado, sin_nube):
    assert asyncio.run(agentes.enrutar(texto, "admin"))[0] == esperado
    assert sin_nube == []  # sin ambigüedad no se gasta la nube


def test_usuario_nunca_va_a_seguridad(sin_nube):
    aid, _ = asyncio.run(agentes.enrutar("Escanea los puertos y dime las vulnerabilidades", "usuario"))
    assert aid == "aria"
    assert all("seguridad" not in c for _, c in sin_nube)


def test_empate_pregunta_a_la_nube_y_respeta_el_rol(monkeypatch):
    vistos = []

    async def clasif(texto, candidatos):
        vistos.append(candidatos)
        return "seguridad"  # la nube «se equivoca» o la manipulan: no debe valer para un usuario
    texto = "¿Es seguro el router? ¿Cuánto dinero me costaría uno nuevo?"
    assert asyncio.run(agentes.enrutar(texto, "usuario", clasif))[0] != "seguridad"
    assert "seguridad" not in vistos[-1]
    assert asyncio.run(agentes.enrutar("router de 50 euros", "admin", clasif))[0] in ("seguridad", "finanzas", "redes")


def test_clasificacion_de_una_linea(monkeypatch):
    class Nube(cerebros.Proveedor):
        id, nombre, nube = "n", "n", True

        async def ronda(self, msgs, con_tools=True, sistema=None, **_):
            assert con_tools is False and "clasificador" in sistema
            yield {"type": "token", "text": "redes"}
    monkeypatch.setattr(cerebros, "cadena", lambda: [Nube()])
    assert asyncio.run(agentes.clasificar_con_nube("¿va lento internet y cuánto pago?", ["finanzas", "redes"])) == "redes"


def test_herramientas_por_agente_y_rol():
    fin = agentes.obtener("finanzas")
    assert agentes.herramientas(fin, "usuario") == set(fin.herramientas)
    redes = agentes.obtener("redes")
    assert agentes.herramientas(redes, "usuario") == {"estado_red", "fecha_hora", "estado_servicios",
                                                      "estado_bloqueador", "dispositivos_vpn", "recordar",
                                                      "olvidar", "buscar_en_internet", "recordatorio",
                                                      "mis_recordatorios", "borrar_recordatorio", "resumir_enlace"}
    # memoria y búsqueda en todos los agentes; ARIA general conserva también noticias y tiempo
    for a in agentes.AGENTES.values():
        assert {"recordar", "olvidar", "buscar_en_internet"} <= agentes.herramientas(a, "admin"), a.id
    assert {"noticias", "tiempo"} <= agentes.herramientas(agentes.obtener("aria"), "usuario")
    assert agentes.herramientas(agentes.obtener("aria"), "admin") == tools.generales()
    seg = agentes.obtener("seguridad")
    assert "informe_seguridad" in agentes.herramientas(seg, "admin")
    assert agentes.herramientas(seg, "usuario") & agentes.SEGURIDAD_TOOLS == set()
    assert not (agentes.obtener("aria").herramientas & agentes.FINANZAS_TOOLS)


def test_ejecutar_respeta_agente_y_uid(admin):
    # herramienta fuera del agente activo
    r = asyncio.run(tools.ejecutar("pausar_bloqueador", {"minutos": 5}, "admin", solo={"fecha_hora"}))
    assert "No tienes permiso" in r
    # el usuario no puede pedir seguridad aunque el modelo la invente
    assert "No tienes permiso" in asyncio.run(tools.ejecutar("informe_seguridad", {}, "usuario"))
    # el modelo no puede inyectar otro uid
    r = asyncio.run(tools.ejecutar("registrar_movimiento", {"concepto": "Café", "importe": -2, "uid": 999},
                                   "usuario", uid=admin["id"]))
    assert "Apuntado" in r
    from aria import finanzas
    assert finanzas.listar(999) == [] and len(finanzas.listar(admin["id"])) == 1
    assert "qué usuario" in asyncio.run(tools.ejecutar("resumen_mes", {}, "usuario"))


class Eco(cerebros.Proveedor):
    def __init__(self):
        self.id, self.nombre, self.nube = "eco", "Eco", True
        self.vistos = []

    def modelo(self):
        return "m"

    async def ronda(self, msgs, con_tools=True, rol="admin", nombre=None, herramientas=None, sistema=None):
        self.vistos.append({"herramientas": herramientas, "sistema": sistema, "ultimo": msgs[-1]["content"]})
        yield {"type": "token", "text": "ok"}


def test_conversar_con_prefijo_insignia_y_persistencia(admin, monkeypatch, sin_nube):
    eco = Eco()
    monkeypatch.setattr(cerebros, "cadena", lambda: [eco])
    evs = correr(chat.conversar(admin, None, "@finanzas ¿cuánto llevo gastado?"))
    ag = next(e for e in evs if e["type"] == "agente")
    assert ag["id"] == "finanzas" and ag["nombre"] == "Finanzas"
    assert eco.vistos[0]["ultimo"] == "¿cuánto llevo gastado?"
    assert "Finanzas" in eco.vistos[0]["sistema"] and "registrar_movimiento" in eco.vistos[0]["herramientas"]
    conv = db.obtener(evs[0]["id"], admin["id"])
    assert conv["mensajes"][-1]["agente"] == "finanzas"


def test_usuario_con_arroba_seguridad_recibe_aviso(ana, monkeypatch, sin_nube):
    eco = Eco()
    monkeypatch.setattr(cerebros, "cadena", lambda: [eco])
    evs = correr(chat.conversar(ana, None, "@seguridad escanea la red"))
    assert any(e["type"] == "aviso" and "solo para administradores" in e["text"] for e in evs)
    assert next(e for e in evs if e["type"] == "agente")["id"] == "aria"
    assert not (eco.vistos[0]["herramientas"] & agentes.SEGURIDAD_TOOLS)


def test_agente_de_la_conversacion(admin, ana, monkeypatch, sin_nube):
    eco = Eco()
    monkeypatch.setattr(cerebros, "cadena", lambda: [eco])
    evs = correr(chat.conversar(admin, None, "hola", "redes"))
    cid = evs[0]["id"]
    assert db.obtener(cid, admin["id"])["agente"] == "redes"
    evs = correr(chat.conversar(admin, cid, "otra cosa"))
    assert next(e for e in evs if e["type"] == "agente")["id"] == "redes"
    # un usuario no puede fijar seguridad en su conversación
    evs = correr(chat.conversar(ana, None, "hola", "seguridad"))
    assert db.obtener(evs[0]["id"], ana["id"])["agente"] == "aria"


def test_cerebro_preferido():
    a, b = Eco(), Eco()
    b.id = "gemini"
    assert [p.id for p in cerebros.con_preferido([a, b], "gemini")] == ["gemini", "eco"]
    assert [p.id for p in cerebros.con_preferido([a, b], "no-existe")] == ["eco", "gemini"]


def test_local_sigue_filtrando_por_palabras_con_agente():
    # el cerebro local de Finanzas solo recibe las herramientas que casan con el mensaje
    fin = agentes.herramientas(agentes.obtener("finanzas"), "usuario")
    assert tools.relevantes("Cuéntame un chiste") & fin == set()
    assert "resumen_mes" in tools.relevantes("¿Cuánto he gastado este mes?") & fin
    assert "registrar_movimiento" in tools.relevantes("Apunta que he gastado 12 euros en Mercadona") & fin
    assert "estado_presupuestos" in tools.relevantes("¿Cómo voy con el presupuesto?") & fin
    redes = agentes.herramientas(agentes.obtener("redes"), "admin")
    assert "test_velocidad" in tools.relevantes("haz un test de velocidad") & redes
    assert "medir_latencia" in tools.relevantes("¿qué ping tengo?") & redes


def test_api_agentes_y_selector(admin, ana):
    from tests.test_permisos import cliente_de
    assert {a["id"] for a in cliente_de(ana).get("/api/agentes").json()["agentes"]} == {"aria", "finanzas", "redes"}
    cid = db.crear(ana["id"])
    c = cliente_de(ana)
    assert c.patch(f"/api/conversations/{cid}", json={"agente": "seguridad"}).status_code == 403
    assert c.patch(f"/api/conversations/{cid}", json={"agente": "finanzas"}).status_code == 200
    assert c.post("/api/chat", json={"message": "x", "agente": "seguridad"}).status_code == 403
    assert c.post("/api/chat", json={"message": "x", "agente": "raro"}).status_code == 400
    cid_admin = db.crear(admin["id"])
    assert c.patch(f"/api/conversations/{cid_admin}", json={"agente": "finanzas"}).status_code == 404
