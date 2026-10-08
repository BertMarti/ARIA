"""Rutinas: horario en español, límites, permisos por rol, IDOR, solo nube, solo herramientas de consulta,
tiempo máximo, entrega por canales y nada de disparos dobles."""
import asyncio
import json
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from aria import agentes, auth, avisos, cerebros, chat, db, main, rutinas, tiempo, tools, usuarios
from aria.rutinas import RutinaError

LAN = "https://192.168.1.50"


def correr(c):
    return asyncio.run(c)


def cliente_de(u) -> TestClient:
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    monkeypatch.setattr(rutinas, "_en_curso", set())
    rutinas.iniciar()
    from aria import api_rutinas
    for n in ("_lim_cambios", "_lim_ejecutar"):
        v = getattr(api_rutinas, n)
        monkeypatch.setattr(api_rutinas, n, avisos.Limitador(v.n, v.ventana))


@pytest.fixture
def buzon(monkeypatch):
    recibidos = []

    async def tg(uid, aviso):
        recibidos.append(("telegram", uid, aviso))
        return True

    async def push(uid, aviso):
        recibidos.append(("push", uid, aviso))
        return True
    monkeypatch.setattr(avisos, "_CANALES", {"telegram": tg, "push": push})
    return recibidos


def L(y, mo, d, h=12, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=tiempo.zona())


BASE = {"nombre": "Tiempo", "prompt": "Dime el tiempo de hoy en Ronda y 3 titulares de tecnología",
        "horario": "todos los días a las 8:00", "canal": "telegram", "agente": "aria"}


# --- Horario en español ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("texto,esperado", [
    ("todos los días a las 8", {"tipo": "diaria", "hora": "08:00", "dias": []}),
    ("a diario a las 7:30", {"tipo": "diaria", "hora": "07:30", "dias": []}),
    ("de lunes a viernes a las 7 y media", {"tipo": "diaria", "hora": "07:30", "dias": [0, 1, 2, 3, 4]}),
    ("los lunes y jueves a las 9 de la noche", {"tipo": "diaria", "hora": "21:00", "dias": [0, 3]}),
    ("los fines de semana a las 10", {"tipo": "diaria", "hora": "10:00", "dias": [5, 6]}),
    ("cada sábado a las 11:15", {"tipo": "diaria", "hora": "11:15", "dias": [5]}),
    ("cada 3 horas", {"tipo": "cada", "horas": 3}),
    ("cada hora", {"tipo": "cada", "horas": 1}),
    ("cada dos horas", {"tipo": "cada", "horas": 2}),
])
def test_interpretar_horario(texto, esperado):
    assert rutinas.interpretar_horario(texto) == esperado


@pytest.mark.parametrize("texto", ["cada 10 minutos", "cada media hora", "cada 200 horas", "todos los días", "", "nunca"])
def test_horarios_no_validos(texto):
    with pytest.raises(RutinaError):
        rutinas.normalizar_horario(texto)


def test_normalizar_dict():
    assert rutinas.normalizar_horario({"tipo": "diaria", "hora": "08:00", "dias": [0, 1, 2, 3, 4, 5, 6]})["dias"] == []
    for malo in ({"tipo": "diaria", "hora": "25:00"}, {"tipo": "diaria", "hora": "08:00", "dias": [7]},
                 {"tipo": "diaria", "hora": "08:00", "dias": [True]}, {"tipo": "cada", "horas": 0},
                 {"tipo": "cada", "horas": "x"}, {"tipo": "cron"}, None, 5):
        with pytest.raises(RutinaError):
            rutinas.normalizar_horario(malo)


def test_describir():
    d = rutinas.describir
    assert d({"tipo": "diaria", "hora": "08:00", "dias": []}) == "todos los días a las 08:00"
    assert d({"tipo": "diaria", "hora": "07:30", "dias": [0, 1, 2, 3, 4]}) == "de lunes a viernes a las 07:30"
    assert d({"tipo": "diaria", "hora": "09:00", "dias": [0, 3]}) == "los lunes y jueves a las 09:00"
    assert d({"tipo": "cada", "horas": 1}) == "cada hora" and d({"tipo": "cada", "horas": 6}) == "cada 6 horas"


def test_siguiente():
    h = {"tipo": "diaria", "hora": "08:00", "dias": []}
    assert rutinas.siguiente(h, L(2026, 10, 7, 7, 59)) == L(2026, 10, 7, 8, 0)
    assert rutinas.siguiente(h, L(2026, 10, 7, 8, 0)) == L(2026, 10, 8, 8, 0)  # estrictamente después
    lab = {"tipo": "diaria", "hora": "08:00", "dias": [0, 1, 2, 3, 4]}
    assert rutinas.siguiente(lab, L(2026, 10, 9, 9, 0)) == L(2026, 10, 12, 8, 0)  # viernes -> lunes
    # Cambio de hora (25/10/2026): sigue a las 08:00 locales.
    assert rutinas.siguiente(h, L(2026, 10, 25, 7, 0)) == L(2026, 10, 25, 8, 0)
    cada = {"tipo": "cada", "horas": 3}
    ref = L(2026, 10, 7, 12, 0)
    assert rutinas.siguiente(cada, ref) == L(2026, 10, 7, 15, 0)
    previa = L(2026, 10, 7, 3, 0).timestamp()  # se perdieron varias: va a la siguiente del mismo ritmo
    assert rutinas.siguiente(cada, ref, previa) == L(2026, 10, 7, 15, 0)
    assert rutinas.siguiente(cada, ref, L(2026, 10, 7, 13, 0).timestamp()) == L(2026, 10, 7, 13, 0)


# --- CRUD, límites y roles -------------------------------------------------------------------------------------------
def test_crear_listar_editar_borrar(admin):
    r = rutinas.crear(admin["id"], "admin", BASE, ref=L(2026, 10, 7, 9))
    assert r["descripcion"] == "todos los días a las 08:00" and r["activa"]
    assert r["proxima"] == L(2026, 10, 8, 8).timestamp()
    r2 = rutinas.actualizar(admin["id"], "admin", r["id"], {"activa": False})
    assert not r2["activa"] and r2["nombre"] == "Tiempo"
    r3 = rutinas.actualizar(admin["id"], "admin", r["id"], {"horario": "cada 2 horas", "activa": True}, ref=L(2026, 10, 7, 9))
    assert r3["activa"] and r3["proxima"] == L(2026, 10, 7, 11).timestamp()
    assert [x["id"] for x in rutinas.listar(admin["id"])] == [r["id"]]
    assert rutinas.buscar(admin["id"], "tiempo")[0]["id"] == r["id"]
    assert rutinas.borrar(admin["id"], r["id"]) and rutinas.listar(admin["id"]) == []


def test_validaciones(admin):
    for cambio, trozo in (({"nombre": ""}, "nombre"), ({"prompt": " "}, "qué debe hacer"),
                          ({"nombre": "x" * 61}, "largo"), ({"prompt": "x" * 1001}, "largo"),
                          ({"canal": "email"}, "canal"), ({"agente": "hacker"}, "agente"),
                          ({"horario": "cada 5 minutos"}, "mínimo")):
        with pytest.raises(RutinaError, match=trozo):
            rutinas.crear(admin["id"], "admin", {**BASE, **cambio})
    with pytest.raises(RutinaError):
        rutinas.actualizar(admin["id"], "admin", rutinas.crear(admin["id"], "admin", BASE)["id"], {"activa": "sí"})


def test_maximo_por_usuario(admin, ana):
    for i in range(rutinas.MAX_POR_USUARIO):
        rutinas.crear(admin["id"], "admin", {**BASE, "nombre": f"R{i}"})
    with pytest.raises(RutinaError, match="10 rutinas"):
        rutinas.crear(admin["id"], "admin", BASE)
    assert rutinas.crear(ana["id"], "usuario", BASE)  # el límite es por usuario


def test_agente_limitado_por_rol(ana, admin):
    with pytest.raises(RutinaError, match="administradores"):
        rutinas.crear(ana["id"], "usuario", {**BASE, "agente": "seguridad"})
    assert rutinas.crear(ana["id"], "usuario", {**BASE, "agente": "finanzas"})["agente"] == "finanzas"
    assert rutinas.crear(admin["id"], "admin", {**BASE, "agente": "seguridad"})["agente"] == "seguridad"


# --- API e IDOR -----------------------------------------------------------------------------------------------------
def test_api_crud(ana):
    c = cliente_de(ana)
    r = c.post("/api/rutinas", json={**BASE, "horario": {"tipo": "diaria", "hora": "07:30", "dias": [0, 2, 4]}})
    assert r.status_code == 200, r.text
    rid = r.json()["rutina"]["id"]
    datos = c.get("/api/rutinas").json()
    assert [x["id"] for x in datos["rutinas"]] == [rid]
    assert "seguridad" not in {a["id"] for a in datos["agentes"]} and datos["limites"]["max"] == 10
    assert c.patch(f"/api/rutinas/{rid}", json={"activa": False}).json()["rutina"]["activa"] is False
    assert c.patch(f"/api/rutinas/{rid}", json={"agente": "seguridad"}).status_code == 400
    assert c.post("/api/rutinas", json={**BASE, "canal": "fax"}).status_code == 400
    assert c.delete(f"/api/rutinas/{rid}").status_code == 200
    assert c.get("/api/rutinas").json()["rutinas"] == []


def test_idor_rutinas(admin, ana, monkeypatch):
    lanzadas = []
    monkeypatch.setattr(rutinas, "en_segundo_plano", lambda coro: (lanzadas.append(1), coro.close()))
    r = rutinas.crear(admin["id"], "admin", BASE)
    bea = cliente_de(ana)
    assert bea.get("/api/rutinas").json()["rutinas"] == []                      # no la ve
    assert bea.patch(f"/api/rutinas/{r['id']}", json={"nombre": "mía"}).status_code == 404  # no la edita
    assert bea.patch(f"/api/rutinas/{r['id']}", json={"activa": False}).status_code == 404  # ni la pausa
    assert bea.post(f"/api/rutinas/{r['id']}/ejecutar").status_code == 404       # no la ejecuta
    assert bea.delete(f"/api/rutinas/{r['id']}").status_code == 404              # no la borra
    assert rutinas.obtener(admin["id"], r["id"])["nombre"] == "Tiempo" and not lanzadas
    assert rutinas.obtener(ana["id"], r["id"]) is None
    assert cliente_de(admin).post(f"/api/rutinas/{r['id']}/ejecutar").status_code == 200 and lanzadas == [1]


def test_ejecutar_api_limitado_y_sin_duplicar(admin, monkeypatch):
    monkeypatch.setattr(rutinas, "en_segundo_plano", lambda coro: coro.close())
    r = rutinas.crear(admin["id"], "admin", BASE)
    c = cliente_de(admin)
    rutinas._en_curso.add(r["id"])
    assert c.post(f"/api/rutinas/{r['id']}/ejecutar").status_code == 409
    rutinas._en_curso.clear()
    codigos = [c.post(f"/api/rutinas/{r['id']}/ejecutar").status_code for _ in range(8)]
    assert codigos.count(200) == 6 and codigos[-1] == 429


# --- Ejecución --------------------------------------------------------------------------------------------------------
class Prov:
    def __init__(self, id_, nube, texto="Hoy 22 °C en Ronda."):
        self.id, self.nombre, self.nube, self.texto = id_, id_, nube, texto
        self.ofrecidas = []

    def modelo(self):
        return "m"

    def etiqueta(self):
        return f"{self.id} · m"

    async def ronda(self, msgs, con_tools=True, rol="admin", nombre=None, herramientas=None, sistema=None, extra=""):
        self.ofrecidas.append(set(herramientas) if herramientas is not None else None)
        yield {"type": "token", "text": self.texto}


@pytest.fixture
def cerebros_falsos(monkeypatch):
    local, nube = Prov("local", False, "SOY EL LOCAL"), Prov("ollama", True)
    monkeypatch.setattr(cerebros, "cadena", lambda: [local, nube])

    async def enrutar(texto, rol, clasificador=None):
        return "aria", "general"
    monkeypatch.setattr(agentes, "enrutar", enrutar)
    return local, nube


def test_ejecutar_solo_nube_y_solo_consultas(admin, buzon, cerebros_falsos):
    local, nube = cerebros_falsos
    r = rutinas.crear(admin["id"], "admin", BASE)
    res = correr(rutinas.ejecutar(rutinas.obtener(admin["id"], r["id"])))
    assert res["estado"] == "ok" and "22 °C" in res["texto"] and "Rutina «Tiempo»" in res["texto"]
    assert local.ofrecidas == []                               # el local nunca se usa
    ofrecidas = nube.ofrecidas[0]
    assert ofrecidas and ofrecidas <= tools.RUTINAS            # solo herramientas de consulta
    for peligrosa in ("pausar_bloqueador", "crear_dispositivo_vpn", "desactivar_dispositivo_vpn", "recordar",
                      "olvidar", "recordatorio", "borrar_recordatorio", "crear_rutina", "borrar_rutina",
                      "registrar_movimiento", "escanear_red", "test_velocidad"):
        assert peligrosa not in ofrecidas
    assert [c for c, *_ in buzon] == ["telegram"]              # canal de la rutina
    assert avisos.listar(admin["id"])["avisos"][0]["tipo"] == "rutina"  # y en la campana
    g = rutinas.obtener(admin["id"], r["id"])
    assert g["ultimo_estado"] == "ok" and g["conv_id"]
    conv = db.obtener(g["conv_id"], admin["id"])
    assert conv["titulo"] == "Rutina · Tiempo" and conv["mensajes"][-1]["content"] == "Hoy 22 °C en Ronda."
    # La siguiente ejecución sustituye la conversación anterior (nadie escribió en ella)
    correr(rutinas.ejecutar(rutinas.obtener(admin["id"], r["id"])))
    assert db.obtener(g["conv_id"], admin["id"]) is None
    assert len([c for c in db.listar(admin["id"]) if c["titulo"] == "Rutina · Tiempo"]) == 1


def test_conversacion_seguida_por_el_usuario_se_conserva(admin, buzon, cerebros_falsos):
    r = rutinas.crear(admin["id"], "admin", BASE)
    correr(rutinas.ejecutar(rutinas.obtener(admin["id"], r["id"])))
    cid = rutinas.obtener(admin["id"], r["id"])["conv_id"]
    db.anadir(cid, "user", "¿y mañana?")
    correr(rutinas.ejecutar(rutinas.obtener(admin["id"], r["id"])))
    assert db.obtener(cid, admin["id"]) is not None


def test_usuario_solo_sus_herramientas(ana, buzon, cerebros_falsos):
    _, nube = cerebros_falsos
    r = rutinas.crear(ana["id"], "usuario", BASE)
    correr(rutinas.ejecutar(rutinas.obtener(ana["id"], r["id"])))
    assert nube.ofrecidas[0] <= tools.permitidas("usuario") & tools.RUTINAS
    assert "informe_seguridad" not in nube.ofrecidas[0]


def test_ejecutar_rechaza_herramienta_no_permitida(admin):
    res = correr(tools.ejecutar("pausar_bloqueador", {"minutos": 5}, "admin", uid=admin["id"],
                                solo=agentes.herramientas(agentes.obtener("aria"), "admin") & tools.RUTINAS))
    assert "permiso" in res


def test_sin_nube_se_salta_con_nota(admin, buzon, monkeypatch):
    local = Prov("local", False)
    monkeypatch.setattr(cerebros, "cadena", lambda: [local])
    r = rutinas.crear(admin["id"], "admin", {**BASE, "canal": "web"})
    res = correr(rutinas.ejecutar(rutinas.obtener(admin["id"], r["id"])))
    assert res["estado"] == "sin_nube" and local.ofrecidas == []
    assert buzon == []                                          # canal web: solo la campana
    av = avisos.listar(admin["id"])["avisos"][0]
    assert "solo responde el cerebro local" in av["texto"]


def test_tiempo_maximo(admin, buzon, monkeypatch, cerebros_falsos):
    monkeypatch.setattr(rutinas, "TIMEOUT_S", 0.05)

    async def lento(u, r):
        await asyncio.sleep(5)
    monkeypatch.setattr(rutinas, "_correr", lento)
    r = rutinas.crear(admin["id"], "admin", {**BASE, "canal": "ambos"})
    res = correr(rutinas.ejecutar(rutinas.obtener(admin["id"], r["id"])))
    assert res["estado"] == "error" and "tardó demasiado" in res["texto"]
    assert sorted(c for c, *_ in buzon) == ["push", "telegram"]
    assert r["id"] not in rutinas._en_curso


def test_resultado_largo_se_recorta(admin, buzon, monkeypatch):
    largo = ("Línea con datos.\n" * 400)
    monkeypatch.setattr(cerebros, "cadena", lambda: [Prov("ollama", True, largo)])
    r = rutinas.crear(admin["id"], "admin", BASE)
    res = correr(rutinas.ejecutar(rutinas.obtener(admin["id"], r["id"])))
    assert len(res["texto"]) < rutinas.MAX_RESULTADO + 100 and "sigue en el chat" in res["texto"]


# --- Planificador: sin disparos dobles ----------------------------------------------------------------------------------
def test_planificador_una_vez_por_hora_programada(admin, buzon, cerebros_falsos):
    r = rutinas.crear(admin["id"], "admin", BASE, ref=L(2026, 10, 7, 7))
    t = L(2026, 10, 7, 8, 0, ).timestamp() + 20
    assert correr(rutinas.disparar_vencidas(t, esperar=True)) == [r["id"]]
    assert correr(rutinas.disparar_vencidas(t + 20, esperar=True)) == []         # el siguiente tick
    assert rutinas.obtener(admin["id"], r["id"])["proxima"] == L(2026, 10, 8, 8).timestamp()
    # «Reinicio» a mitad: la próxima no llegó a guardarse, pero la ejecución ya estaba anotada.
    with db._con() as con:
        con.execute("UPDATE rutinas SET proxima=? WHERE id=?", (L(2026, 10, 7, 8).timestamp(), r["id"]))
    assert correr(rutinas.disparar_vencidas(t + 40, esperar=True)) == []
    assert len(buzon) == 1
    assert rutinas.obtener(admin["id"], r["id"])["proxima"] == L(2026, 10, 8, 8).timestamp()


def test_pausada_no_se_dispara(admin, buzon, cerebros_falsos):
    r = rutinas.crear(admin["id"], "admin", BASE, ref=L(2026, 10, 7, 7))
    rutinas.actualizar(admin["id"], "admin", r["id"], {"activa": False})
    assert correr(rutinas.disparar_vencidas(L(2026, 10, 7, 9).timestamp(), esperar=True)) == []


def test_atrasada_se_salta(admin, buzon, cerebros_falsos):
    r = rutinas.crear(admin["id"], "admin", BASE, ref=L(2026, 10, 7, 7))
    assert correr(rutinas.disparar_vencidas(L(2026, 10, 7, 14).timestamp(), esperar=True)) == []
    g = rutinas.obtener(admin["id"], r["id"])
    assert g["ultimo_estado"] == "omitida" and g["proxima"] == L(2026, 10, 8, 8).timestamp() and buzon == []


def test_usuario_desactivado_no_ejecuta(ana, buzon, cerebros_falsos):
    r = rutinas.crear(ana["id"], "usuario", BASE, ref=L(2026, 10, 7, 7))
    usuarios.actualizar(ana["id"], activo=False)
    correr(rutinas.disparar_vencidas(L(2026, 10, 7, 8, 1).timestamp(), esperar=True))
    assert buzon == [] and rutinas.obtener(ana["id"], r["id"])["ultima"] is None


def test_tick_llama_a_las_rutinas(monkeypatch):
    vistas = []

    async def disparar(ahora=None, esperar=False):
        vistas.append(ahora)
        return []

    async def nada(*a, **k):
        return []
    from aria import recordatorios
    monkeypatch.setattr(avisos, "_CHEQUEOS", {})
    monkeypatch.setattr(recordatorios, "disparar_vencidos", nada)
    monkeypatch.setattr(avisos, "briefings_programados", nada)
    monkeypatch.setattr(rutinas, "disparar_vencidas", disparar)
    correr(avisos.tick(1234.0))
    assert vistas == [1234.0]


def test_borrar_usuario_borra_sus_rutinas(ana):
    rutinas.crear(ana["id"], "usuario", BASE)
    with db._con() as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("DELETE FROM usuarios WHERE id=?", (ana["id"],))
    assert rutinas.listar(ana["id"]) == []


# --- Herramientas del chat -------------------------------------------------------------------------------------------
def test_herramientas_de_chat(ana):
    uid = ana["id"]
    res = correr(tools.ejecutar("crear_rutina", {"nombre": "Noticias", "prompt": "3 titulares de tecnología",
                                                "horario": "de lunes a viernes a las 7:30", "uid": 999}, "usuario", uid=uid))
    assert "creada" in res and "de lunes a viernes a las 07:30" in res
    assert rutinas.listar(uid)[0]["nombre"] == "Noticias"
    assert "Noticias" in correr(tools.ejecutar("mis_rutinas", {}, "usuario", uid=uid))
    assert "solo para administradores" in correr(tools.ejecutar(
        "crear_rutina", {"nombre": "x", "prompt": "y", "horario": "cada hora", "agente": "seguridad"}, "usuario", uid=uid))
    assert "mínimo" in correr(tools.ejecutar("crear_rutina", {"nombre": "x", "prompt": "y", "horario": "cada 5 minutos"},
                                              "usuario", uid=uid))
    assert "borrada" in correr(tools.ejecutar("borrar_rutina", {"id_o_nombre": "noticias"}, "usuario", uid=uid))
    assert rutinas.listar(uid) == []


def test_herramientas_de_chat_no_tocan_las_de_otro(admin, ana):
    r = rutinas.crear(admin["id"], "admin", BASE)
    assert "No encuentro" in correr(tools.ejecutar("borrar_rutina", {"id_o_nombre": str(r["id"])}, "usuario", uid=ana["id"]))
    assert rutinas.obtener(admin["id"], r["id"])


def test_intenciones_de_rutinas():
    assert "crear_rutina" in tools.relevantes("crea una rutina que cada día a las 8 me diga el tiempo")
    assert "mis_rutinas" in tools.relevantes("¿qué rutinas tengo?")
    assert {"borrar_rutina", "mis_rutinas"} <= tools.relevantes("borra la rutina del tiempo")
    assert "crear_rutina" not in tools.relevantes("borra la rutina del tiempo")
    assert "resumir_enlace" in tools.relevantes("resume https://example.com/noticia")
    for charla in ("hola", "explícame qué es un DNS", "cuéntame un chiste"):
        assert not (tools.relevantes(charla) & (tools.GESTION_RUTINAS | {"resumir_enlace"}))


def test_permisos_de_herramientas():
    assert tools.GESTION_RUTINAS <= tools.permitidas("usuario")
    assert "resumir_enlace" in tools.permitidas("usuario")
    assert not (tools.GESTION_RUTINAS & tools.RUTINAS - {"mis_rutinas"})
    assert {"crear_rutina", "resumir_enlace"} <= agentes.herramientas(agentes.obtener("aria"), "usuario")
