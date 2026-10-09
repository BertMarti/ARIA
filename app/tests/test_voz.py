"""Voz: validación de subidas, relevo Groq → local, limpieza de texto para TTS, WebSocket y permisos."""
import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from aria import auth, main, usuarios, voz

LAN = "https://192.168.1.50"
WS = "wss://192.168.1.50/api/voz/despertar"
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 200
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 100


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
    monkeypatch.setattr(voz, "limite_stt", voz.Limitador(100, 60))
    monkeypatch.setattr(voz, "limite_stt_hora", voz.Limitador(1000, 3600))
    monkeypatch.setattr(voz, "limite_tts", voz.Limitador(100, 60))
    monkeypatch.setattr(voz, "_espera_groq", 0.0)
    monkeypatch.setattr(voz, "_escuchas", {})
    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)  # la síntesis con Gemini se prueba en test_voz_gemini.py


def red_falsa(monkeypatch, groq, local, llamadas):
    """Sustituye la red: `groq` y `local` son funciones request -> httpx.Response."""
    def manejar(req: httpx.Request):
        llamadas.append(req.url.host)
        return groq(req) if req.url.host == "api.groq.com" else local(req)
    transporte = httpx.MockTransport(manejar)
    monkeypatch.setattr(voz, "_cliente", lambda t: httpx.AsyncClient(transport=transporte))


# --- Validación ---------------------------------------------------------------------------------
@pytest.mark.parametrize("tipo,datos,estado", [
    ("text/plain", WEBM, 415), ("application/octet-stream", WEBM, 415), (None, WEBM, 415),
    ("audio/webm", b"", 400), ("audio/webm", b"<html>no es audio</html>", 415),
    ("audio/wav", WEBM, 415), ("audio/webm", WEBM[:4] + b"\x00" * voz.MAX_BYTES, 413),
])
def test_validar_audio_rechaza(tipo, datos, estado):
    with pytest.raises(voz.AudioError) as e:
        voz.validar_audio(tipo, datos)
    assert e.value.estado == estado


def test_validar_audio_acepta():
    assert voz.validar_audio("audio/webm;codecs=opus", WEBM) == "webm"
    assert voz.validar_audio("audio/wav", WAV) == "wav"
    assert voz.validar_audio("audio/ogg; codecs=opus", b"OggS" + b"\x00" * 50) == "ogg"
    assert voz.validar_audio("audio/mp4", b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 50) == "m4a"


def test_subida_grande_se_corta_antes_de_leerla(admin):
    r = cliente_de(admin).post("/api/voz/transcribir", content=b"x" * 10,
                               headers={"Content-Type": "audio/webm", "Content-Length": str(voz.MAX_BYTES + 1)})
    assert r.status_code == 413


def test_subida_de_tipo_no_audio(admin):
    r = cliente_de(admin).post("/api/voz/transcribir", content=b"hola", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415


# --- Relevo de proveedores ----------------------------------------------------------------------
def test_groq_primero(monkeypatch, admin):
    llamadas = []
    red_falsa(monkeypatch, lambda r: httpx.Response(200, json={"text": " Hola ARIA "}),
              lambda r: httpx.Response(500), llamadas)
    r = cliente_de(admin).post("/api/voz/transcribir", content=WEBM, headers={"Content-Type": "audio/webm"})
    assert r.status_code == 200 and r.json()["texto"] == "Hola ARIA" and r.json()["proveedor"] == "groq"
    assert llamadas == ["api.groq.com"]


@pytest.mark.parametrize("fallo", [
    lambda r: httpx.Response(429, headers={"retry-after": "120"}, json={"error": "rate limit"}),
    lambda r: httpx.Response(401),
    lambda r: httpx.Response(503),
    lambda r: (_ for _ in ()).throw(httpx.ConnectError("sin red")),
])
def test_groq_falla_y_se_usa_local(monkeypatch, admin, fallo):
    llamadas = []
    red_falsa(monkeypatch, fallo, lambda r: httpx.Response(200, json={"texto": "qué tiempo hace"}), llamadas)
    r = cliente_de(admin).post("/api/voz/transcribir", content=WEBM, headers={"Content-Type": "audio/webm"})
    assert r.status_code == 200 and r.json() == {**r.json(), "texto": "qué tiempo hace", "proveedor": "local"}
    assert llamadas == ["api.groq.com", "voz"]
    # Tras el fallo, Groq queda en espera y la siguiente va directa a local.
    llamadas.clear()
    cliente_de(admin).post("/api/voz/transcribir", content=WEBM, headers={"Content-Type": "audio/webm"})
    assert llamadas == ["voz"]


def test_sin_clave_va_a_local(monkeypatch, admin):
    monkeypatch.delenv("GROQ_API_KEY")
    llamadas = []
    red_falsa(monkeypatch, lambda r: httpx.Response(200, json={"text": "no"}),
              lambda r: httpx.Response(200, json={"texto": "local"}), llamadas)
    r = cliente_de(admin).post("/api/voz/transcribir", content=WEBM, headers={"Content-Type": "audio/webm"})
    assert r.json()["proveedor"] == "local" and llamadas == ["voz"]


def test_todo_caido_da_503(monkeypatch, admin):
    def caido(r):
        raise httpx.ConnectError("caído")
    red_falsa(monkeypatch, caido, caido, [])
    r = cliente_de(admin).post("/api/voz/transcribir", content=WEBM, headers={"Content-Type": "audio/webm"})
    assert r.status_code == 503 and "error" in r.json()


def test_el_audio_va_a_groq_como_multipart(monkeypatch, admin):
    vistos = {}

    def groq(req):
        vistos["auth"] = req.headers["authorization"]
        vistos["cuerpo"] = req.content
        return httpx.Response(200, json={"text": "ok"})
    red_falsa(monkeypatch, groq, lambda r: httpx.Response(500), [])
    cliente_de(admin).post("/api/voz/transcribir", content=WEBM, headers={"Content-Type": "audio/webm;codecs=opus"})
    assert vistos["auth"] == "Bearer clave-de-prueba"
    assert b'filename="audio.webm"' in vistos["cuerpo"] and b"whisper-large-v3-turbo" in vistos["cuerpo"]
    assert b'name="language"\r\n\r\nes' in vistos["cuerpo"]


def test_limite_por_usuario(monkeypatch, admin, ana):
    monkeypatch.setattr(voz, "limite_stt", voz.Limitador(2, 60))
    red_falsa(monkeypatch, lambda r: httpx.Response(200, json={"text": "x"}), lambda r: httpx.Response(500), [])
    a = cliente_de(admin)
    codigos = [a.post("/api/voz/transcribir", content=WEBM, headers={"Content-Type": "audio/webm"}).status_code
               for _ in range(3)]
    assert codigos == [200, 200, 429]
    # Otro usuario tiene su propio cupo.
    assert cliente_de(ana).post("/api/voz/transcribir", content=WEBM,
                                headers={"Content-Type": "audio/webm"}).status_code == 200


def test_limitador_ventana():
    t = [0.0]
    lim = voz.Limitador(2, 60, reloj=lambda: t[0])
    assert lim.esperar("u") == 0 and lim.esperar("u") == 0
    assert lim.esperar("u") > 0
    t[0] = 61
    assert lim.esperar("u") == 0


# --- Texto para TTS -------------------------------------------------------------------------------
@pytest.mark.parametrize("entrada,esperado", [
    ("**Hola**, soy *ARIA*.", "Hola, soy ARIA."),
    ("Mira [la guía](https://example.com/guia) ahora", "Mira la guía ahora"),
    ("Enlace: https://example.com/x?y=1 fin", "Enlace: fin"),
    ("# Título\n- uno\n- dos\n1. tres", "Título\nuno\ndos\ntres"),
    ("Código:\n```bash\nrm -rf /\n```\nListo", "Código:\nListo"),
    ("Usa `docker ps` 🚀✅", "Usa docker ps"),
    ("| A | B |\n|---|---|\n| 1 | 2 |", "A, B\n1, 2"),
    ("Temperatura: 48,5 °C · RAM 40 %", "Temperatura: 48,5 °C · RAM 40 %"),
    ("snake_case y 2*3", "snake_case y 2 3"),
])
def test_limpiar_para_voz(entrada, esperado):
    assert voz.limpiar_para_voz(entrada) == esperado


def test_limpiar_para_voz_recorta_en_frase():
    texto = "Esta es una frase. " * 200
    r = voz.limpiar_para_voz(texto, 100)
    assert len(r) <= 100 and r.endswith(".")


@pytest.mark.parametrize("entrada,esperado", [
    ("Aria, ¿qué tiempo hace en Ronda?", "¿qué tiempo hace en Ronda?"),
    ("aria qué hora es", "qué hora es"),
    ("Oye, Aria. Pon música", "Pon música"),
    ("¿Quién es Aria?", "¿Quién es Aria?"),
    ("Arial es una fuente", "Arial es una fuente"),
    ("María, pon música", "María, pon música"),
])
def test_quitar_despertar(entrada, esperado):
    assert voz.quitar_despertar(entrada) == esperado


def test_hablar(monkeypatch, ana):
    vistos = {}

    async def sintetizar(texto, vel, pref=None):
        vistos.update(texto=texto, vel=vel)
        return b"RIFF....WAVE", "gemini"
    monkeypatch.setattr(voz, "sintetizar_info", sintetizar)
    r = cliente_de(ana).post("/api/voz/hablar", json={"texto": "**Hola** [aquí](https://x.es)", "velocidad": 9})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert vistos == {"texto": "Hola aquí", "vel": voz.VEL_MAX}
    assert cliente_de(ana).post("/api/voz/hablar", json={"texto": "🚀"}).status_code == 400
    assert cliente_de(ana).post("/api/voz/hablar", json={"texto": 3}).status_code == 400


# --- Permisos y cabeceras -------------------------------------------------------------------------
@pytest.mark.parametrize("metodo,ruta", [("GET", "/api/voz/estado"), ("POST", "/api/voz/transcribir"),
                                         ("POST", "/api/voz/hablar")])
def test_voz_requiere_sesion(metodo, ruta):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    assert c.request(metodo, ruta, content=WEBM, headers={"Content-Type": "audio/webm"}).status_code == 401


def test_voz_disponible_para_usuario(monkeypatch, ana):
    async def no():
        return False
    monkeypatch.setattr(voz, "voz_local_ok", no)
    r = cliente_de(ana).get("/api/voz/estado")
    assert r.status_code == 200 and {k: r.json()[k] for k in ("groq", "local")} == {"groq": True, "local": False}


def test_post_de_voz_con_origen_ajeno(admin):
    r = cliente_de(admin).post("/api/voz/hablar", json={"texto": "hola"}, headers={"Origin": "https://malo.example"})
    assert r.status_code == 403


def test_cabecera_permissions_policy(admin):
    r = cliente_de(admin).get("/")
    assert r.headers["permissions-policy"] == "microphone=(self), camera=(), geolocation=(self)"
    assert "unsafe-inline" not in r.headers["content-security-policy"]
    login = TestClient(main.app, base_url=LAN).get("/login")
    assert "microphone=(self)" in login.headers["permissions-policy"]


# --- WebSocket «manos libres» --------------------------------------------------------------------
@pytest.fixture
def puente_falso(monkeypatch):
    async def retransmitir(ws, uid):
        await ws.send_json({"type": "listo"})
        await ws.close()
    monkeypatch.setattr(voz, "retransmitir", retransmitir)


@pytest.mark.parametrize("cabeceras", [{}, {"Origin": "https://malo.example"}, {"Origin": "null"},
                                      {"Origin": "http://evil.192.168.1.50"}])
def test_ws_rechaza_origen(puente_falso, admin, cabeceras):
    with pytest.raises(WebSocketDisconnect) as e:
        with cliente_de(admin).websocket_connect(WS, headers=cabeceras):
            pass
    assert e.value.code == 1008


def test_ws_rechaza_sin_sesion(puente_falso):
    c = TestClient(main.app, base_url=LAN)
    with pytest.raises(WebSocketDisconnect) as e:
        with c.websocket_connect(WS, headers={"Origin": LAN}):
            pass
    assert e.value.code == 1008


def test_ws_rechaza_sesion_falsificada(puente_falso):
    c = TestClient(main.app, base_url=LAN)
    c.cookies.set(auth.COOKIE, "eyJ1IjoxfQ.firma-falsa")
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect(WS, headers={"Origin": LAN}):
            pass


@pytest.mark.parametrize("quien", ["admin", "ana"])
def test_ws_acepta_ambos_roles(puente_falso, quien, request):
    u = request.getfixturevalue(quien)
    with cliente_de(u).websocket_connect(WS, headers={"Origin": LAN}) as ws:
        assert ws.receive_json() == {"type": "listo"}


def test_ws_una_escucha_por_usuario(puente_falso, monkeypatch, admin):
    monkeypatch.setattr(voz, "_escuchas", {admin["id"]: 1})
    with pytest.raises(WebSocketDisconnect) as e:
        with cliente_de(admin).websocket_connect(WS, headers={"Origin": LAN}):
            pass
    assert e.value.code == 1013


def test_origen_ws_permitido():
    assert voz.origen_ws_permitido("https://aria.tu-dominio.com", "aria.tu-dominio.com")
    assert voz.origen_ws_permitido("https://192.168.1.50", "192.168.1.50")
    assert not voz.origen_ws_permitido(None, "192.168.1.50")
    assert not voz.origen_ws_permitido("https://aria.tu-dominio.com", "192.168.1.50")
    assert not voz.origen_ws_permitido("chrome-extension://abc", "abc")
