import asyncio

import pytest
from fastapi.testclient import TestClient

from aria import auth, main, usuarios, voz

LAN = "https://192.168.1.50"


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def cliente(u):
    c = TestClient(main.app, base_url=LAN)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def test_estilo_en_espanol_de_espana_y_dulce():
    e = voz._estilo(1.0)
    assert e.startswith("Lee en español con acento de España") and "muy dulce" in e and e.endswith(": ")
    assert "latinoamericano" in voz._estilo(1.0, {"acento": "es-US"})
    assert voz.preferencia({"voz": "Inventada", "tono": "x"}) == voz.PREF_DEFECTO


def test_peticion_a_gemini_lleva_voz_e_idioma(monkeypatch):
    enviado = {}

    class R:
        status_code = 200
        headers = {}
        def json(self):
            import base64
            return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;rate=24000",
                                                                            "data": base64.b64encode(b"\0\0" * 24000).decode()}}]}}]}

    class Cliente:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json, headers):
            enviado.update(json); return R()
    monkeypatch.setattr(voz, "_cliente", lambda t: Cliente())
    asyncio.run(voz._gemini_modelo("m", False, "Hola, buenos días a todos", 1.0, {"voz": "Achernar", "tono": "tierna"}))
    sc = enviado["generationConfig"]["speechConfig"]
    assert sc["languageCode"] == "es-ES" and sc["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Achernar"
    assert "casi susurrando" in enviado["contents"][0]["parts"][0]["text"]


def test_preferencias_por_usuario_y_api(ana):
    c = cliente(ana)
    d = c.get("/api/voz/voces").json()
    assert d["actual"] == voz.PREF_DEFECTO and len(d["voces"]) >= 10 and {t["id"] for t in d["tonos"]} >= {"dulce", "tierna"}
    assert c.post("/api/voz/preferencias", json={"voz": "Sulafat", "tono": "tierna", "otra": 1}).json() == \
        {"voz": "Sulafat", "tono": "tierna", "acento": "es-ES"}
    assert voz.preferencias_de(ana["id"])["voz"] == "Sulafat"
    assert voz.preferencias_de(usuarios.por_identificador("admin")["id"]) == voz.PREF_DEFECTO


def test_muestra_se_guarda_y_no_repite_peticion(ana, monkeypatch):
    llamadas = []
    async def falso(texto, vel, pref=None):
        llamadas.append(pref["voz"]); return b"RIFF-falso"
    monkeypatch.setattr(voz, "_gemini", falso)
    monkeypatch.setattr(voz, "gemini_tts_disponible", lambda: True)
    c = cliente(ana)
    for _ in range(2):
        r = c.post("/api/voz/muestra", json={"voz": "Despina", "tono": "dulce", "acento": "es-ES"})
        assert r.status_code == 200 and r.content == b"RIFF-falso"
    assert llamadas == ["Despina"]


def test_muestra_sin_gemini_da_error_claro(ana, monkeypatch):
    monkeypatch.setattr(voz, "gemini_tts_disponible", lambda: False)
    r = cliente(ana).post("/api/voz/muestra", json={"voz": "Kore"})
    assert r.status_code == 503 and "Gemini" in r.json()["error"]


def test_hablar_avisa_si_usa_la_voz_local(ana, monkeypatch):
    async def info(texto, vel, pref=None):
        return b"RIFF-local", "local"
    monkeypatch.setattr(voz, "sintetizar_info", info)
    monkeypatch.setattr(voz, "gemini_vuelve", lambda: 1_800_000_000)
    voz.guardar_preferencias(ana["id"], {"voz": "Achernar"})
    r = cliente(ana).post("/api/voz/hablar", json={"texto": "Hola"})
    assert r.status_code == 200 and r.headers["x-voz-motor"] == "local"
    assert r.headers["x-voz-nombre"] == "Achernar" and r.headers["x-voz-vuelve"] == "1800000000"


def test_cuota_diaria_se_respeta_entera(monkeypatch):
    monkeypatch.setattr(voz, "_espera_gemini", {})
    voz._anotar_fallo_gemini("modelo-x", 50000, "HTTP 429")
    assert voz._espera_gemini["modelo-x"] - voz._ahora() > 40000
    voz._anotar_fallo_gemini("modelo-y", 50000, "red")
    assert voz._espera_gemini["modelo-y"] - voz._ahora() <= 3600
