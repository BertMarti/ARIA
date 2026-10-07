"""Memoria a largo plazo: recuerdos por usuario, herramientas, aprendizaje automático, contexto del prompt."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from aria import aprender, auth, cerebros, chat, config, db, main, memoria, tools, usuarios

LAN = "https://192.168.1.50"


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


def correr(coro):
    return asyncio.run(coro)


# --- CRUD por usuario e IDOR ---------------------------------------------------------------------
def test_crud_basico(admin):
    rec, nuevo = memoria.anadir(admin["id"], "Mi equipo de fútbol es el Betis")
    assert nuevo and rec["origen"] == "usuario"
    assert [r["texto"] for r in memoria.listar(admin["id"])] == ["Mi equipo de fútbol es el Betis"]
    assert memoria.editar(admin["id"], rec["id"], "Su equipo es el Real Betis")["texto"] == "Su equipo es el Real Betis"
    assert memoria.borrar(admin["id"], rec["id"]) and memoria.listar(admin["id"]) == []


def test_idor_recuerdos_por_api(admin, ana):
    r_admin, _ = memoria.anadir(admin["id"], "Lucía vive en Sevilla")
    r_ana, _ = memoria.anadir(ana["id"], "Ana es alérgica a las nueces")
    ca, cb = cliente_de(ana), cliente_de(admin)
    assert [r["texto"] for r in ca.get("/api/memoria").json()["recuerdos"]] == ["Ana es alérgica a las nueces"]
    assert ca.delete(f"/api/memoria/{r_admin['id']}").status_code == 404
    assert ca.patch(f"/api/memoria/{r_admin['id']}", json={"texto": "hackeado"}).status_code == 404
    assert memoria.obtener(admin["id"], r_admin["id"])["texto"] == "Lucía vive en Sevilla"
    assert cb.delete(f"/api/memoria/{r_ana['id']}").status_code == 404
    assert memoria.obtener(ana["id"], r_ana["id"]) is not None
    # «Borrar toda mi memoria» solo borra la de quien llama
    assert ca.delete("/api/memoria").status_code == 200
    assert memoria.listar(ana["id"]) == [] and len(memoria.listar(admin["id"])) == 1


def test_api_anadir_ajustes_y_diario(admin, ana):
    c = cliente_de(ana)
    assert c.post("/api/memoria", json={"texto": "Prefiero el café sin azúcar"}).json()["creado"] is True
    assert c.post("/api/memoria", json={"texto": "Prefiero el café sin azúcar"}).json()["creado"] is False
    assert c.post("/api/memoria", json={"texto": "x" * 301}).status_code == 400
    assert c.post("/api/memoria", json={"texto": "mi contraseña es hunter22"}).status_code == 400
    assert c.post("/api/memoria/ajustes", json={"aprender": "no"}).status_code == 400
    assert c.post("/api/memoria/ajustes", json={"aprender": False}).json() == {"aprender": False}
    assert c.get("/api/memoria").json()["aprender"] is False and memoria.aprende(admin["id"]) is True
    memoria.guardar_dia(ana["id"], "2026-10-06", "- Preguntó por la VPN")
    memoria.guardar_dia(admin["id"], "2026-10-06", "- Del admin")
    assert [d["resumen"] for d in c.get("/api/memoria").json()["diario"]] == ["- Preguntó por la VPN"]
    assert c.delete("/api/diario/2026-10-05").status_code == 404
    assert cliente_de(ana).delete("/api/diario/2026-10-06").status_code == 200
    assert memoria.dia(admin["id"], "2026-10-06") is not None


def test_generar_diario_es_solo_admin(ana):
    assert cliente_de(ana).post("/api/diario/generar", json={}).status_code == 403


def test_borrar_usuario_borra_su_memoria(admin):
    u = usuarios.crear("tmp@example.com", "Tmp", "usuario", "clave-larga-tmp")
    memoria.anadir(u["id"], "Dato de prueba temporal")
    memoria.guardar_dia(u["id"], "2026-10-06", "- algo")
    usuarios.borrar(u["id"])
    assert memoria.listar(u["id"]) == [] and memoria.ultimos_dias(u["id"]) == []


# --- Herramientas recordar / olvidar ---------------------------------------------------------------
@pytest.mark.parametrize("rol", ["admin", "usuario"])
def test_herramientas_para_todo_rol(admin, rol):
    memoria.uid_actual.set(admin["id"])
    assert {"recordar", "olvidar"} <= tools.permitidas(rol)
    r = correr(tools.ejecutar("recordar", {"dato": "Mi equipo de fútbol es el Betis"}, rol))
    assert "Anotado" in r
    assert [x["texto"] for x in memoria.listar(admin["id"])] == ["Mi equipo de fútbol es el Betis"]
    assert "Ya lo tenía" in correr(tools.ejecutar("recordar", {"dato": "mi equipo de futbol es el betis"}, rol))
    assert "Olvidado" in correr(tools.ejecutar("olvidar", {"dato_o_id": "mi equipo es el Betis"}, rol))
    assert memoria.listar(admin["id"]) == []
    assert "No tengo ningún recuerdo" in correr(tools.ejecutar("olvidar", {"dato_o_id": "nada de esto"}, rol))


def test_tools_solo_tocan_al_usuario_actual(admin, ana):
    r, _ = memoria.anadir(admin["id"], "Lucía toca la guitarra")
    memoria.uid_actual.set(ana["id"])
    assert "No tengo ningún recuerdo" in correr(tools.ejecutar("olvidar", {"dato_o_id": str(r["id"])}, "usuario"))
    assert "No tengo ningún recuerdo" in correr(tools.ejecutar("olvidar", {"dato_o_id": "guitarra"}, "usuario"))
    assert memoria.obtener(admin["id"], r["id"]) is not None


def test_olvidar_por_id_y_ambiguo(admin):
    a, _ = memoria.anadir(admin["id"], "Tiene un perro llamado Toby")
    b, _ = memoria.anadir(admin["id"], "Tiene un perro labrador en casa de sus padres")
    memoria.uid_actual.set(admin["id"])
    assert "varios" in correr(tools.ejecutar("olvidar", {"dato_o_id": "perro"}))
    assert len(memoria.listar(admin["id"])) == 2
    assert "Olvidado" in correr(tools.ejecutar("olvidar", {"dato_o_id": str(a["id"])}))
    assert [x["id"] for x in memoria.listar(admin["id"])] == [b["id"]]


def test_tools_sin_usuario_y_secretos():
    memoria.uid_actual.set(None)
    assert "No sé quién eres" in correr(tools.ejecutar("recordar", {"dato": "algo largo de verdad"}))


def test_recordar_rechaza_secretos(admin):
    memoria.uid_actual.set(admin["id"])
    assert "No guardo contraseñas" in correr(tools.ejecutar("recordar", {"dato": "mi contraseña es hunter2"}))
    assert memoria.listar(admin["id"]) == []


@pytest.mark.parametrize("texto,tool", [
    ("Recuerda que mi equipo de fútbol es el Betis", "recordar"), ("Apunta que cenamos a las 9", "recordar"),
    ("Acuérdate de que soy vegetariano", "recordar"), ("Olvida que me gusta el Betis", "olvidar"),
    ("No recuerdes lo de mi cumpleaños", "olvidar"),
])
def test_intenciones_de_memoria(texto, tool):
    assert tool in tools.relevantes(texto)


@pytest.mark.parametrize("texto", ["¿Recuerdas qué te dije?", "No te olvides de saludar", "Hola", "Cuéntame un chiste"])
def test_memoria_no_se_activa_en_charla(texto):
    assert not tools.relevantes(texto) & tools.MEMORIA


# --- Secretos --------------------------------------------------------------------------------------
@pytest.mark.parametrize("texto", [
    "Mi contraseña es hunter2", "la password del wifi es casa1234", "mi clave de la tarjeta es 4321",
    "Su token es abcdefghijklmnopqrstuvwxyz0123456789", "api key sk-abcdef1234567890abcdef", "Tarjeta 4111 1111 1111 1111",
    "Su DNI es 12345678Z", "IBAN ES9121000418450200051332", "PIN 4444", "su NIE es X1234567L",
    "ghp_abcdefghijklmnopqrstuv1234", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4",
])
def test_detecta_secretos(texto):
    assert memoria.parece_secreto(texto)


@pytest.mark.parametrize("texto", ["Su equipo es el Betis", "Vive en Sevilla desde 2015", "Tiene 2 gatos y un perro",
                                   "Cumple años el 12 de marzo", "Prefiere la temperatura a 21 grados"])
def test_no_marca_falsos_secretos(texto):
    assert not memoria.parece_secreto(texto)


# --- Aprendizaje automático ---------------------------------------------------------------------------
def test_parsear_json_valido_e_invalido():
    assert aprender.parsear('{"hechos": ["Le gusta el jazz", "Vive en Sevilla"]}') == ["Le gusta el jazz", "Vive en Sevilla"]
    assert aprender.parsear('```json\n{"hechos": ["A b c"]}\n```') == ["A b c"]
    assert aprender.parsear('Claro: {"hechos": ["Tiene un gato"]} ¡listo!') == ["Tiene un gato"]
    assert aprender.parsear('["Tiene un gato"]') == ["Tiene un gato"]
    assert aprender.parsear('{"hechos": "no es lista"}') == []
    assert aprender.parsear('{"hechos": [1, null, {"a": 1}, "  "]}') == []
    assert aprender.parsear("esto no es json") == [] and aprender.parsear("") == []


def test_guardar_filtra_secretos_duplicados_y_limita_a_3(admin):
    memoria.anadir(admin["id"], "Su equipo de fútbol es el Betis")
    cand = ["Su equipo de fútbol es el Betis", "Su contraseña es hunter22", "Tiene un perro", "Vive en Sevilla",
            "Le encanta el jazz", "Odia madrugar"]
    assert aprender.guardar(admin["id"], cand) == ["Tiene un perro", "Vive en Sevilla", "Le encanta el jazz"]
    origenes = {r["texto"]: r["origen"] for r in memoria.listar(admin["id"])}
    assert origenes["Tiene un perro"] == "auto" and origenes["Su equipo de fútbol es el Betis"] == "usuario"
    assert "Su contraseña es hunter22" not in origenes


def test_dedupe_aproximado(admin):
    memoria.anadir(admin["id"], "Su equipo de fútbol es el Betis")
    assert aprender.guardar(admin["id"], ["Su equipo de futbol es el Betis.", "su equipo de fútbol es el betis!"]) == []


def _p(n):
    """Palabra de 8 letras distinta para cada n (para que el dedupe no las confunda)."""
    import random
    r = random.Random(n)
    return "".join(r.choice("bcdfghjklmnpqrstvwxyz") + r.choice("aeiou") for _ in range(4))


def test_tope_de_200_borra_primero_los_auto_menos_usados(admin):
    u = admin["id"]
    for i in range(190):
        memoria.anadir(u, f"Auto {_p(i)} {_p(i * 7 + 1)} {_p(i * 13 + 5)}", "auto")
    for i in range(10):
        memoria.anadir(u, f"Usuario {_p(i + 500)} {_p(i * 11 + 3)} {_p(i * 17 + 9)}", "usuario")
    assert memoria.contar(u) == 200
    memoria.contexto(u, "A", "auto", True)  # marca como usados los que caben en el contexto
    nuevo, creado = memoria.anadir(u, "Tiene una bicicleta roja de montaña", "auto")
    assert creado and memoria.contar(u) == 200
    textos = {r["texto"] for r in memoria.listar(u)}
    assert "Tiene una bicicleta roja de montaña" in textos
    assert sum(1 for t in textos if t.startswith("Usuario ")) == 10  # los del usuario no se tocan


def test_tope_sin_autos_rechaza_al_usuario_y_descarta_auto(admin):
    u = admin["id"]
    with memoria.closing(db._con()) as con, con:
        con.executemany("INSERT INTO recuerdos (user_id, texto, origen, creado) VALUES (?,?,?,?)",
                        [(u, f"Recuerdo del usuario {i}", "usuario", 1000.0 + i) for i in range(200)])
    with pytest.raises(memoria.MemoriaError, match="máximo"):
        memoria.anadir(u, "Uno más que no cabe", "usuario")
    assert memoria.anadir(u, "Otro automático que no cabe", "auto") == (None, False)
    assert memoria.contar(u) == 200


class Nube(cerebros.Proveedor):
    id, nombre, nube = "n", "Nube", True

    def __init__(self, respuesta):
        self.respuesta, self.llamadas = respuesta, 0

    def modelo(self):
        return "m"

    async def ronda(self, msgs, con_tools=True, **_):
        self.llamadas += 1
        yield {"type": "token", "text": self.respuesta}


class Local(Nube):
    id, nombre, nube = "local", "Local", False


def test_extraer_con_cerebro_nube(admin, monkeypatch):
    n = Nube('{"hechos": ["Su equipo es el Betis", "Su contraseña es 1234"]}')
    monkeypatch.setattr(cerebros, "cadena", lambda: [n, Local("")])
    r = correr(aprender.extraer(admin["id"], "Lucía", "Hola, soy del Betis desde que nací, por cierto"))
    assert r == ["Su equipo es el Betis"] and n.llamadas == 1


def test_sin_nube_no_se_extrae_nada(admin, monkeypatch):
    loc = Local('{"hechos": ["Algo importante de verdad"]}')
    monkeypatch.setattr(cerebros, "cadena", lambda: [loc])
    assert correr(aprender.extraer(admin["id"], "Lucía", "Soy del Betis desde que nací, ya lo sabes")) == []
    assert loc.llamadas == 0 and memoria.listar(admin["id"]) == []


def test_interruptor_apagado_no_guarda_ni_llama(admin, monkeypatch):
    n = Nube('{"hechos": ["Su equipo es el Betis"]}')
    monkeypatch.setattr(cerebros, "cadena", lambda: [n, Local("")])
    memoria.fijar_aprender(admin["id"], False)
    assert correr(aprender.extraer(admin["id"], "Lucía", "Soy del Betis desde que nací, ya lo sabes")) == []
    assert n.llamadas == 0 and memoria.listar(admin["id"]) == []

    async def programar():
        return aprender.programar(admin["id"], "Lucía", "Soy del Betis desde que nací, ya lo sabes")
    assert correr(programar()) is None


def test_mensajes_cortos_no_gastan_cuota(admin, monkeypatch):
    n = Nube('{"hechos": ["x"]}')
    monkeypatch.setattr(cerebros, "cadena", lambda: [n])
    assert correr(aprender.extraer(admin["id"], "A", "hola")) == [] and n.llamadas == 0


def test_la_nube_que_falla_pasa_a_la_siguiente(admin, monkeypatch):
    class Mala(Nube):
        id = "mala"

        async def ronda(self, msgs, con_tools=True, **_):
            raise cerebros.ProveedorError("cuota")
            yield
    buena = Nube('{"hechos": ["Tiene un loro"]}')
    monkeypatch.setattr(cerebros, "cadena", lambda: [Mala(""), buena])
    monkeypatch.setattr(cerebros, "registrar_fallo", lambda *a: None)
    assert correr(aprender.extraer(admin["id"], "A", "Mi loro se llama Paco y habla mucho conmigo")) == ["Tiene un loro"]


def test_chat_programa_extraccion_y_no_aprende_de_olvidar(admin, monkeypatch):
    llamadas = []
    monkeypatch.setattr(aprender, "programar", lambda uid, nombre, texto: llamadas.append(texto))

    async def responder(msgs, rol="admin", quien=None, **_):
        yield {"type": "token", "text": "vale"}
        yield {"type": "fin"}
    monkeypatch.setattr(chat, "responder", responder)

    async def hablar(t):
        return [e async for e in chat.conversar(admin, None, t)]
    correr(hablar("Soy del Betis desde que nací, ya lo sabes"))
    correr(hablar("Olvida que soy del Betis, por favor"))
    assert llamadas == ["Soy del Betis desde que nací, ya lo sabes"]


# --- Presupuesto del prompt y relevancia -------------------------------------------------------------
def _llenar(uid, n=40):
    for i in range(n):
        memoria.anadir(uid, f"Dato {i} de Lucía: le gusta mucho el tema número {i} y suele hablar de ello a diario", "usuario")


def test_presupuesto_local_300(admin):
    _llenar(admin["id"])
    memoria.guardar_dia(admin["id"], "2026-10-06", "- Preguntó por la VPN")
    bloque = memoria.contexto(admin["id"], "Lucía", "hola qué tal", nube=False)
    assert 0 < len(bloque) <= 300 and bloque.count(";") <= 4 and "VPN" not in bloque
    with memoria.closing(db._con()) as con:
        assert con.execute("SELECT COUNT(*) FROM recuerdos WHERE usado IS NOT NULL").fetchone()[0] <= 5


def test_presupuesto_nube(admin):
    _llenar(admin["id"], 60)
    for d in range(1, 6):
        memoria.guardar_dia(admin["id"], f"2026-10-0{d}", "\n".join(f"- Punto {i} del día {d} " + "x" * 80 for i in range(5)))
    bloque = memoria.contexto(admin["id"], "Lucía", "hola", nube=True)
    hechos, diario = bloque.split("\n\n")
    assert len(hechos) <= 1200 and len(diario) <= 900
    assert diario.count("\n- 2026-") == 3 and "2026-10-05" in diario and "2026-10-03" in diario and "2026-10-02" not in diario


def test_relevancia_primero_los_que_comparten_palabras(admin):
    u = admin["id"]
    memoria.anadir(u, "Su equipo de fútbol es el Betis")
    memoria.anadir(u, "Tiene un perro llamado Toby")
    memoria.anadir(u, "Vive en Sevilla")  # el más reciente
    pedido = memoria.ordenar_por_relevancia(memoria.listar(u), "¿Cómo se llama mi perro?")
    assert pedido[0]["texto"] == "Tiene un perro llamado Toby"
    assert [h["texto"] for h in memoria.ordenar_por_relevancia(memoria.listar(u), "hola")][0] == "Vive en Sevilla"
    assert memoria.contexto(u, "Lucía", "¿Qué equipo de fútbol me gusta?", False).startswith("Sabes de Lucía: Su equipo")


def test_contexto_marca_usado_y_vacio_sin_datos(admin, ana):
    assert memoria.contexto(admin["id"], "A", "hola", True) == ""
    r, _ = memoria.anadir(admin["id"], "Le gusta el jazz")
    assert memoria.obtener(admin["id"], r["id"])["usado"] is None
    assert "Le gusta el jazz" in memoria.contexto(admin["id"], "A", "hola", True)
    assert memoria.obtener(admin["id"], r["id"])["usado"] is not None
    assert memoria.contexto(ana["id"], "Ana", "hola", True) == ""  # nada de otro usuario


def test_prompt_de_nube_y_local_reciben_su_bloque(admin, monkeypatch):
    memoria.anadir(admin["id"], "Su equipo es el Betis")
    memoria.guardar_dia(admin["id"], "2026-10-06", "- Preguntó por la VPN")
    vistos = {}

    class Espia(Nube):
        async def ronda(self, msgs, con_tools=True, rol="admin", nombre=None, extra=""):
            vistos[self.id] = extra
            yield {"type": "token", "text": "ok"}

    class EspiaLocal(Espia):
        id, nombre, nube = "local", "Local", False
    monkeypatch.setattr(cerebros, "cadena", lambda: [Espia(""), EspiaLocal("")])
    memoria.uid_actual.set(admin["id"])
    correr(_todo(chat.responder([{"role": "user", "content": "hola"}], "admin", "Lucía")))
    assert "Lo que sabes de Lucía" in vistos["n"] and "2026-10-06" in vistos["n"]
    assert vistos["n"].count("Betis") == 1


async def _todo(gen):
    return [e async for e in gen]


def test_config_system_prompt_con_extra():
    assert config.system_prompt(True, "Ana", True, "BLOQUE").endswith("\n\nBLOQUE")
    assert "BLOQUE" not in config.system_prompt(True, "Ana", True)
