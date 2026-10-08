"""Interfaz mínima de voz para Telegram (y cualquier canal que no sea el navegador).

    transcribir(datos, mime) -> str            nota de voz -> texto
    sintetizar(texto) -> (bytes, mime) | None  texto -> audio (OGG/Opus si aria-voz lo sabe hacer)

Por debajo usa `voz.py` (Groq Whisper y, si falla, faster-whisper local en aria-voz; Gemini «Leda» y, de respaldo, Piper para hablar).
Si el módulo de voz no estuviera, se transcribe directamente con la API de Groq (GROQ_API_KEY) y se responde
solo con texto. El audio solo vive en memoria."""
import logging
import os

import httpx

log = logging.getLogger("aria.voz_puente")

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MAX_BYTES = 1_000_000


class VozError(Exception):
    """Error legible (en español)."""


def _voz():
    try:
        from . import voz
        return voz
    except ImportError:  # pragma: no cover - sin la función de voz
        return None


async def transcribir(datos: bytes, mime: str = "audio/ogg") -> str:
    v = _voz()
    if v is not None:
        try:
            ext = v.validar_audio(mime, datos)
            return (await v.transcribir(datos, ext, v.tipo_base(mime)))["texto"]
        except v.AudioError as e:
            raise VozError(e.mensaje) from None
    clave = os.environ.get("GROQ_API_KEY", "")
    if not clave:
        raise VozError("No puedo transcribir notas de voz: falta la clave de Groq o el servicio de voz.")
    if len(datos) > MAX_BYTES:
        raise VozError("La nota de voz es demasiado larga.")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(GROQ_URL, headers={"Authorization": f"Bearer {clave}"},
                             files={"file": ("voz.ogg", datos, mime)},
                             data={"model": "whisper-large-v3-turbo", "language": "es", "response_format": "json"})
        r.raise_for_status()
        return str(r.json().get("text", "")).strip()
    except (httpx.HTTPError, ValueError):
        raise VozError("No se pudo transcribir la nota de voz.") from None


async def sintetizar(texto: str) -> tuple | None:
    """(audio, mime) o None si no hay síntesis. Pide OGG/Opus a aria-voz; si devuelve WAV, se usa tal cual."""
    v = _voz()
    if v is None:
        return None
    limpio = v.limpiar_para_voz(texto, v.MAX_TTS)
    if not limpio:
        return None
    if v.gemini_tts_disponible():  # misma voz que en la web (Gemini «Leda»), convertida a OGG en aria-voz
        try:
            wav = await v.sintetizar(limpio, 1.0)
            async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5)) as c:
                r = await c.post(f"{v.VOZ_URL}/ogg", content=wav, headers={"Content-Type": "audio/wav"})
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("audio/ogg"):
                return r.content, "audio/ogg"
            return wav, "audio/wav"
        except (v.AudioError, httpx.HTTPError):
            log.warning("No se pudo usar la voz de Gemini para Telegram; se usa la local")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5)) as c:
            r = await c.post(f"{v.VOZ_URL}/tts", json={"texto": limpio, "velocidad": 1.0, "formato": "ogg"})
    except httpx.HTTPError:
        log.warning("aria-voz no responde: la respuesta va solo en texto")
        return None
    tipo = r.headers.get("content-type", "").split(";")[0]
    if r.status_code != 200 or tipo not in ("audio/ogg", "audio/wav"):
        return None
    return r.content, tipo
