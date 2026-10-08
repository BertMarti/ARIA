"""Síntesis de voz: Gemini «Leda» primero y Piper (aria-voz) de respaldo; voz para Telegram."""
import asyncio
import base64
import io
import wave

import httpx
import pytest

from aria import voz, voz_puente


def wav_de(segundos: float, frecuencia: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frecuencia)
        w.writeframes(b"\x00\x00" * int(segundos * frecuencia))
    return buf.getvalue()


PIPER = wav_de(1.0, 22050)
TEXTO = "Hola Lucía, soy Aria. ¿En qué te ayudo?"  # 41 caracteres -> entre 0,8 s y 6,1 s


def respuesta_gemini(datos: bytes, mime: str = "audio/wav") -> dict:
    return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": mime,
                                                                   "data": base64.b64encode(datos).decode()}}]}}]}


@pytest.fixture(autouse=True)
def entorno(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "clave-gemini")
    monkeypatch.delenv("ARIA_TTS", raising=False)
    monkeypatch.setattr(voz, "_espera_gemini", {})
    monkeypatch.setattr(voz, "_cache_tts", voz.OrderedDict())


def montar(monkeypatch, gemini):
    """gemini(request) -> httpx.Response. aria-voz responde siempre con PIPER (o OGG en /ogg)."""
    llamadas = []

    def manejar(req: httpx.Request):
        llamadas.append(req)
        if "generativelanguage" in req.url.host:
            return gemini(req)
        if req.url.path == "/ogg":
            return httpx.Response(200, content=b"OggS" + b"\x00" * 50, headers={"content-type": "audio/ogg"})
        return httpx.Response(200, content=PIPER, headers={"content-type": "audio/wav"})

    transporte = httpx.MockTransport(manejar)
    monkeypatch.setattr(voz, "_cliente", lambda t: httpx.AsyncClient(transport=transporte))
    original = httpx.AsyncClient
    monkeypatch.setattr(voz_puente.httpx, "AsyncClient", lambda **k: original(transport=transporte))
    return llamadas


def test_rota_modelos_si_uno_agota_la_cuota(monkeypatch):
    bueno = wav_de(3.0)
    vistos = []

    def gemini(r):
        vistos.append(r.url.path.split("/")[-1].split(":")[0])
        if len(vistos) == 1:
            return httpx.Response(429, text='{"error": {"details": [{"retryDelay": "4s"}]}}')
        return httpx.Response(200, json=respuesta_gemini(bueno))
    llamadas = montar(monkeypatch, gemini)
    assert asyncio.run(voz.sintetizar(TEXTO, 1.0)) == bueno
    assert vistos == ["gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
    assert voz._espera_gemini["gemini-3.1-flash-tts-preview"] - voz._ahora() == pytest.approx(5, abs=1)
    assert "Say warmly" in llamadas[-1].read().decode()


def test_modelo_plano_no_recibe_estilo(monkeypatch):
    ahora = voz._ahora()
    monkeypatch.setattr(voz, "_espera_gemini", {"gemini-3.1-flash-tts-preview": ahora + 99,
                                                "gemini-2.5-flash-preview-tts": ahora + 99})
    llamadas = montar(monkeypatch, lambda r: httpx.Response(200, json=respuesta_gemini(wav_de(3.0))))
    asyncio.run(voz.sintetizar(TEXTO, 1.0))
    assert "gemini-3.8-flash-tts" in str(llamadas[0].url) and "Say" not in llamadas[0].read().decode()


def test_usa_gemini_con_voz_leda(monkeypatch):
    bueno = wav_de(3.0)
    llamadas = montar(monkeypatch, lambda r: httpx.Response(200, json=respuesta_gemini(bueno)))
    assert asyncio.run(voz.sintetizar(TEXTO, 1.0)) == bueno
    cuerpo = llamadas[0].read().decode()
    assert "Leda" in cuerpo and TEXTO in cuerpo and llamadas[0].headers["x-goog-api-key"] == "clave-gemini"
    assert "clave-gemini" not in str(llamadas[0].url)
    # la segunda vez sale de la caché, sin gastar cuota
    assert asyncio.run(voz.sintetizar(TEXTO, 1.0)) == bueno and len(llamadas) == 1


def test_pcm_crudo_se_envuelve_en_wav(monkeypatch):
    pcm = b"\x00\x00" * 24000 * 2
    montar(monkeypatch, lambda r: httpx.Response(200, json=respuesta_gemini(pcm, "audio/L16;codec=pcm;rate=24000")))
    wav = asyncio.run(voz.sintetizar(TEXTO, 1.0))
    assert wav[:4] == b"RIFF" and voz.duracion_wav(wav) == pytest.approx(2.0)


def test_cuota_agotada_usa_piper_y_espera(monkeypatch):
    llamadas = montar(monkeypatch, lambda r: httpx.Response(429, headers={"retry-after": "90"}))
    assert asyncio.run(voz.sintetizar(TEXTO, 1.0)) == PIPER
    assert not voz.gemini_tts_disponible()
    n = len(llamadas)
    assert asyncio.run(voz.sintetizar("Otra frase distinta.", 1.0)) == PIPER
    assert not any("generativelanguage" in r.url.host for r in llamadas[n:])  # en espera: ni lo intenta


def test_audio_demasiado_largo_usa_piper(monkeypatch):
    # el modelo leyó también las instrucciones o se repitió
    montar(monkeypatch, lambda r: httpx.Response(200, json=respuesta_gemini(wav_de(30.0))))
    assert asyncio.run(voz.sintetizar(TEXTO, 1.0)) == PIPER


def test_respuesta_sin_audio_usa_piper(monkeypatch):
    montar(monkeypatch, lambda r: httpx.Response(200, json={"candidates": []}))
    assert asyncio.run(voz.sintetizar(TEXTO, 1.0)) == PIPER


def test_sin_clave_o_modo_local_no_llama_a_gemini(monkeypatch):
    llamadas = montar(monkeypatch, lambda r: pytest.fail("no debía llamar a Gemini"))
    monkeypatch.setenv("ARIA_TTS", "local")
    assert asyncio.run(voz.sintetizar(TEXTO, 1.0)) == PIPER
    monkeypatch.delenv("ARIA_TTS")
    monkeypatch.delenv("GEMINI_API_KEY")
    assert asyncio.run(voz.sintetizar(TEXTO + " Y más.", 1.0)) == PIPER
    assert all("generativelanguage" not in r.url.host for r in llamadas)


def test_telegram_usa_gemini_convertido_a_ogg(monkeypatch):
    llamadas = montar(monkeypatch, lambda r: httpx.Response(200, json=respuesta_gemini(wav_de(3.0))))
    audio, mime = asyncio.run(voz_puente.sintetizar(TEXTO))
    assert mime == "audio/ogg" and audio[:4] == b"OggS"
    assert [r.url.path for r in llamadas if "generativelanguage" not in r.url.host] == ["/ogg"]


def test_telegram_sin_gemini_usa_piper_ogg(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    llamadas = montar(monkeypatch, lambda r: pytest.fail("no debía llamar a Gemini"))
    asyncio.run(voz_puente.sintetizar(TEXTO))
    assert llamadas[-1].url.path == "/tts" and b'"formato":"ogg"' in llamadas[-1].read().replace(b" ", b"")
