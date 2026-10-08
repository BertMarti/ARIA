"""Diario (planificador, recuperación, resumen extractivo) y resumen de buenos días."""
import asyncio
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from aria import auth, briefing, cerebros, chat, config, db, diario, main, memoria, shield, tiempo, usuarios, vpn

LAN = "https://192.168.1.50"
MAD = ZoneInfo("Europe/Madrid")


def correr(c):
    return asyncio.run(c)


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def cliente_de(u):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def mensaje(uid, texto, cuando: datetime, titulo="Charla", rol="user"):
    """Inserta un mensaje con marca de tiempo concreta."""
    cid = db.crear(uid, titulo)
    with db.closing(db._con()) as con, con:
        con.execute("INSERT INTO mensajes (conv_id, rol, contenido, ts) VALUES (?,?,?,?)", (cid, rol, texto, cuando.timestamp()))
    return cid


class Nube(cerebros.Proveedor):
    id, nombre, nube = "n", "Nube", True

    def __init__(self, texto):
        self.texto = texto

    def modelo(self):
        return "m"

    async def ronda(self, msgs, con_tools=True, **_):
        yield {"type": "token", "text": self.texto}


# --- Fechas --------------------------------------------------------------------------------------
def test_ayer_cruzando_medianoche_en_madrid():
    # 23:30 UTC del 25-oct = 00:30 del 26-oct en Madrid (ya sin horario de verano) -> ayer es el 25
    ref = datetime(2026, 10, 25, 23, 30, tzinfo=timezone.utc)
    assert tiempo.hoy(ref) == date(2026, 10, 26) and tiempo.ayer(ref) == date(2026, 10, 25)
    # 22:30 UTC del 25-oct = 23:30 del 25 en Madrid -> ayer es el 24
    assert tiempo.ayer(datetime(2026, 10, 25, 22, 30, tzinfo=timezone.utc)) == date(2026, 10, 24)


def test_limites_del_dia_con_cambio_de_hora():
    ini, fin = tiempo.limites(date(2026, 10, 25))      # termina el horario de verano: 25 h
    assert fin - ini == 25 * 3600
    ini, fin = tiempo.limites(date(2026, 3, 29))       # empieza: 23 h
    assert fin - ini == 23 * 3600
    assert tiempo.limites(date(2026, 10, 6))[1] - tiempo.limites(date(2026, 10, 6))[0] == 24 * 3600


def test_proxima_ejecucion_0330_local():
    antes = datetime(2026, 10, 24, 22, 0, tzinfo=timezone.utc)   # 00:00 del 25 en Madrid
    assert diario.proxima_ejecucion(antes) == datetime(2026, 10, 25, 3, 30, tzinfo=MAD)
    despues = datetime(2026, 10, 25, 9, 0, tzinfo=MAD)
    p = diario.proxima_ejecucion(despues)
    assert p == datetime(2026, 10, 26, 3, 30, tzinfo=MAD) and p > despues


# --- Diario -----------------------------------------------------------------------------------------
def test_mensajes_de_medianoche_van_al_dia_local_correcto(admin):
    mensaje(admin["id"], "casi medianoche", datetime(2026, 10, 25, 23, 59, tzinfo=MAD))
    mensaje(admin["id"], "pasada la medianoche", datetime(2026, 10, 26, 0, 1, tzinfo=MAD))
    assert diario.usuarios_con_mensajes(date(2026, 10, 25)) == [admin["id"]]
    assert len(diario._mensajes_del_dia(admin["id"], date(2026, 10, 25))[0]) == 1
    assert len(diario._mensajes_del_dia(admin["id"], date(2026, 10, 26))[0]) == 1


def test_resumen_con_cerebro_de_nube(admin, monkeypatch):
    mensaje(admin["id"], "¿Cuántos anuncios se bloquean?", datetime(2026, 10, 6, 12, tzinfo=MAD))
    monkeypatch.setattr(cerebros, "cadena", lambda: [Nube("- Preguntó por los anuncios\n• Quiere revisar la VPN\n" + "- relleno " * 100)])
    assert correr(diario.generar(admin["id"], "Lucía", date(2026, 10, 6))) == "cerebro"
    r = memoria.dia(admin["id"], "2026-10-06")["resumen"]
    assert r.startswith("- Preguntó por los anuncios") and len(r) <= 600
    assert correr(diario.generar(admin["id"], "Lucía", date(2026, 10, 6))) == "existente"


def test_fallback_extractivo_sin_nube(admin, monkeypatch):
    mensaje(admin["id"], "hola", datetime(2026, 10, 6, 12, tzinfo=MAD), titulo="Plan de la VPN")
    mensaje(admin["id"], "otra", datetime(2026, 10, 6, 13, tzinfo=MAD), titulo="Receta de lentejas")
    monkeypatch.setattr(cerebros, "cadena", lambda: [cerebros.PROVEEDORES["local"]])
    assert correr(diario.generar(admin["id"], "A", date(2026, 10, 6))) == "extractivo"
    r = memoria.dia(admin["id"], "2026-10-06")["resumen"]
    assert "Plan de la VPN" in r and "Receta de lentejas" in r


def test_recuperacion_de_dias_perdidos(admin, ana, monkeypatch):
    monkeypatch.setattr(cerebros, "cadena", lambda: [cerebros.PROVEEDORES["local"]])
    for d in (3, 4, 6):
        mensaje(admin["id"], "algo", datetime(2026, 10, d, 10, tzinfo=MAD), titulo=f"Día {d}")
    mensaje(ana["id"], "algo de ana", datetime(2026, 10, 4, 10, tzinfo=MAD), titulo="Ana 4")
    memoria.guardar_dia(admin["id"], "2026-10-04", "- ya existía")
    hecho = correr(diario.ponerse_al_dia(hasta=date(2026, 10, 6), dias=7))
    assert set(hecho) == {"2026-10-03", "2026-10-04", "2026-10-06"}
    assert hecho["2026-10-04"] == {ana["id"]: "extractivo"}          # el del admin no se pisa
    assert memoria.dia(admin["id"], "2026-10-04")["resumen"] == "- ya existía"
    assert memoria.dia(ana["id"], "2026-10-04") and not memoria.dia(ana["id"], "2026-10-03")
    assert correr(diario.ponerse_al_dia(hasta=date(2026, 10, 6), dias=7)) == {}   # idempotente


def test_interruptor_apagado_sin_diario(admin, monkeypatch):
    mensaje(admin["id"], "algo", datetime(2026, 10, 6, 10, tzinfo=MAD))
    memoria.fijar_aprender(admin["id"], False)
    assert correr(diario.generar(admin["id"], "A", date(2026, 10, 6))) == "desactivado"
    assert memoria.dia(admin["id"], "2026-10-06") is None


def test_endpoint_generar_hoy_solo_admin(admin, ana, monkeypatch):
    monkeypatch.setattr(cerebros, "cadena", lambda: [cerebros.PROVEEDORES["local"]])
    mensaje(admin["id"], "hola de hoy", tiempo.ahora(), titulo="Charla de hoy")
    r = cliente_de(admin).post("/api/diario/generar", json={})
    assert r.status_code == 200 and r.json()["resultados"] == {str(admin["id"]): "extractivo"}
    assert "Charla de hoy" in memoria.dia(admin["id"], tiempo.hoy().isoformat())["resumen"]
    assert cliente_de(ana).post("/api/diario/generar", json={}).status_code == 403


# --- Resumen de buenos días ------------------------------------------------------------------------------
@pytest.mark.parametrize("t", ["hola", "Hola", "¡Hola, ARIA!", "buenos días", "Buenos días, ARIA", "buenas tardes",
                               "hola, ¿qué tal?", "Buenas", "hey", "hola buenos días"])
def test_es_saludo(t):
    assert briefing.es_saludo(t)


@pytest.mark.parametrize("t", ["hola, ¿qué temperatura hace?", "buenos días, pon música", "qué tal el Betis",
                               "dime la hora", "", "recuerda que hola"])
def test_no_es_saludo(t):
    assert not briefing.es_saludo(t)


@pytest.fixture
def casa(monkeypatch):
    monkeypatch.setattr(config, "SHIELD_URL", "http://x"); monkeypatch.setattr(config, "SHIELD_PASSWORD", "p")
    monkeypatch.setattr(config, "VPN_USER", "u"); monkeypatch.setattr(config, "VPN_PASSWORD", "p")
    monkeypatch.setattr(config, "VPN_URL", "https://x")
    llamadas = {"n": 0}

    async def dia(d, h):
        llamadas["n"] += 1
        return {"consultas": 1000, "bloqueadas": 250, "porcentaje": 25.0}

    async def clientes():
        ahora = datetime.now(timezone.utc).isoformat()
        return [{"nombre": "Movil", "conectado": True, "ultimo_handshake": ahora},
                {"nombre": "Portatil", "conectado": False, "ultimo_handshake": "2020-01-01T00:00:00Z"}]
    monkeypatch.setattr(shield, "resumen_dia", dia)
    monkeypatch.setattr(vpn, "listar", clientes)
    monkeypatch.setattr(briefing, "ultima_copia", lambda: {"disponible": True, "fecha": "x", "hace": "hace 3 h", "antigua": False})
    return llamadas


def test_briefing_admin_tiene_todo_y_usuario_no(admin, ana, casa):
    memoria.anadir(admin["id"], "Su equipo es el Betis")
    memoria.guardar_dia(admin["id"], tiempo.ayer().isoformat(), "- Revisó la VPN")
    memoria.guardar_dia(ana["id"], tiempo.ayer().isoformat(), "- Preguntó por recetas")
    d = correr(briefing.obtener(admin))
    assert d["casa"]["anuncios"]["bloqueadas"] == 250 and d["casa"]["vpn"]["conectados"] == 1
    assert d["casa"]["vpn"]["ultimas_24h"] == ["Movil"] and d["casa"]["copia"]["hace"] == "hace 3 h"
    assert d["ayer"]["resumen"] == "- Revisó la VPN" and d["recuerdos"] == ["Su equipo es el Betis"]
    assert d["saludo"].endswith(admin["nombre"])
    u = correr(briefing.obtener(ana))
    assert "vpn" not in u["casa"] and "copia" not in u["casa"] and u["casa"]["anuncios"]
    assert u["ayer"]["resumen"] == "- Preguntó por recetas" and u["recuerdos"] == []
    # y por la API, con la cookie de Ana
    j = cliente_de(ana).get("/api/briefing").json()
    assert "vpn" not in j["casa"] and "copia" not in j["casa"] and "vpn" in cliente_de(admin).get("/api/briefing").json()["casa"]


def test_cache_por_dia_y_refrescar(admin, casa):
    correr(briefing.obtener(admin))
    correr(briefing.obtener(admin))
    assert casa["n"] == 1
    correr(briefing.obtener(admin, refrescar=True))
    assert casa["n"] == 2
    # otro día -> se vuelve a construir
    correr(briefing.obtener(admin, ref=datetime.now(MAD) + __import__("datetime").timedelta(days=1)))
    assert casa["n"] == 3


def test_la_cache_de_admin_no_se_filtra_a_usuario_si_cambia_el_rol(admin, casa):
    d = correr(briefing.obtener(admin))
    assert "vpn" in d["casa"]
    assert "vpn" not in briefing.para_rol(d, "usuario")["casa"] and "vpn" in d["casa"]


def test_sin_fuentes_dice_no_disponible(admin, monkeypatch):
    monkeypatch.setattr(config, "COPIAS_REPO", "/no/existe")
    d = correr(briefing.obtener(admin))
    assert d["casa"]["anuncios"] is None and d["casa"]["vpn"] == {"disponible": False}
    assert d["casa"]["copia"] == {"disponible": False} and d["tiempo"] is None
    assert "no está disponible" in briefing.texto_hablado(d)


def test_primer_saludo_del_dia_devuelve_el_resumen(admin, casa, monkeypatch):
    async def responder(*a, **k):
        yield {"type": "token", "text": "respuesta normal"}
        yield {"type": "fin"}
    monkeypatch.setattr(chat, "responder", responder)

    async def hablar(t):
        return [e async for e in chat.conversar(admin, None, t)]
    evs = correr(hablar("Hola"))
    texto = "".join(e.get("text", "") for e in evs if e["type"] == "token")
    assert "Hoy es" in texto and "250 anuncios" in texto and "respuesta normal" not in texto
    assert briefing.saludado_hoy(admin["id"])
    texto2 = "".join(e.get("text", "") for e in correr(hablar("Hola")) if e["type"] == "token")
    assert texto2 == "respuesta normal"        # solo la primera vez del día


def test_tiempo_con_coordenadas_fijas(admin, monkeypatch):
    monkeypatch.setattr(config, "CIUDAD", "Ronda, Málaga"); monkeypatch.setattr(config, "LAT", 36.7423); monkeypatch.setattr(config, "LON", -5.1671)
    visto = {}

    class R:
        def json(self):
            return {"current": {"temperature_2m": 18.4}, "daily": {"weather_code": [3], "temperature_2m_max": [24.2],
                    "temperature_2m_min": [11.0], "precipitation_probability_max": [40]}}

    class C:
        async def __aenter__(s): return s
        async def __aexit__(s, *a): return False
        async def get(s, url, params=None):
            visto["url"], visto["p"] = url, params
            return R()
    monkeypatch.setattr(briefing.httpx, "AsyncClient", lambda **k: C())
    t = correr(briefing._tiempo())
    assert t == {"ciudad": "Ronda", "cielo": "nublado", "max": 24, "min": 11, "lluvia": 40, "actual": 18}
    assert visto["p"]["latitude"] == 36.7423 and "geocoding" not in visto["url"]


def test_geocodificacion_elige_provincia(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CIUDAD", "Ronda, Málaga"); monkeypatch.setattr(config, "LAT", None); monkeypatch.setattr(config, "LON", None)
    res = [{"name": "Ronda", "country_code": "ES", "admin1": "Andalucía", "admin2": "Provincia de Cádiz", "latitude": 1, "longitude": 1},
           {"name": "Ronda", "country_code": "ES", "admin1": "Andalucía", "admin2": "Provincia de Málaga", "latitude": 37.97, "longitude": -4.1},
           {"name": "Ronda", "country_code": "MX", "admin2": "Málaga", "latitude": 2, "longitude": 2}]

    class C:
        async def get(s, url, params=None):
            class R:
                def json(self): return {"results": res}
            return R()
    d = correr(briefing._coordenadas(C()))
    assert d["lat"] == 37.97 and (tmp_path / "ciudad.json").exists()
