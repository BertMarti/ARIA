"""Voz: transcripción (Groq Whisper → aria-voz local), síntesis (Piper en aria-voz) y
utilidades de la escucha «manos libres».

El audio solo vive en memoria durante la petición: nunca se escribe en disco ni en la base
de datos. Groq recibe el audio (si hay clave); si falla, tiene cuota agotada o no hay clave,
se transcribe en local en el contenedor aria-voz.
"""
import logging
import os
import re
import time
import unicodedata
from collections import deque
from urllib.parse import urlparse

import httpx

from . import cerebros

log = logging.getLogger("aria.voz")

VOZ_URL = os.environ.get("ARIA_VOZ_URL", "http://voz:8001").rstrip("/")
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODELO_DEFECTO = "whisper-large-v3-turbo"

MAX_BYTES = 1_000_000      # ~4 min de Opus a 32 kbit/s; el navegador corta a los 30 s
MAX_TTS = 600              # caracteres por petición de síntesis (el navegador trocea)
MAX_TTS_TOTAL = 1500       # lo que se llega a leer de una respuesta
VEL_MIN, VEL_MAX = 0.7, 1.5

# Tipo MIME (sin parámetros) -> extensión que entiende Groq / PyAV
TIPOS = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav",
         "audio/wave": "wav", "audio/mp4": "m4a", "audio/mpeg": "mp3"}


class AudioError(Exception):
    def __init__(self, estado: int, mensaje: str):
        super().__init__(mensaje)
        self.estado, self.mensaje = estado, mensaje


# --- Validación de la subida -------------------------------------------------------------------
def _firma_ok(ext: str, d: bytes) -> bool:
    if ext == "webm":
        return d[:4] == b"\x1a\x45\xdf\xa3"
    if ext == "ogg":
        return d[:4] == b"OggS"
    if ext == "wav":
        return d[:4] == b"RIFF" and d[8:12] == b"WAVE"
    if ext == "m4a":
        return d[4:8] == b"ftyp"
    if ext == "mp3":
        return d[:3] == b"ID3" or (len(d) > 1 and d[0] == 0xFF and d[1] & 0xE0 == 0xE0)
    return False


def tipo_base(content_type: str | None) -> str:
    return (content_type or "").split(";")[0].strip().lower()


def validar_audio(content_type: str | None, datos: bytes) -> str:
    """Devuelve la extensión del audio o lanza AudioError (400/413/415)."""
    ext = TIPOS.get(tipo_base(content_type))
    if not ext:
        raise AudioError(415, "Formato de audio no admitido.")
    if not datos:
        raise AudioError(400, "No llegó audio.")
    if len(datos) > MAX_BYTES:
        raise AudioError(413, "La grabación es demasiado larga.")
    if not _firma_ok(ext, datos):
        raise AudioError(415, "El archivo no es audio válido.")
    return ext


def duracion_wav(datos: bytes) -> float | None:
    """Duración de un WAV PCM (None si no es un WAV que sepamos leer)."""
    import io
    import wave
    try:
        with wave.open(io.BytesIO(datos)) as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError, ZeroDivisionError):
        return None


# --- Limitador por usuario ---------------------------------------------------------------------
class Limitador:
    """Ventana deslizante en memoria: como mucho `n` usos cada `ventana` segundos por clave."""

    def __init__(self, n: int, ventana: float, reloj=time.monotonic):
        self.n, self.ventana, self.reloj = n, ventana, reloj
        self._usos: dict = {}

    def esperar(self, clave) -> int:
        """0 si se permite (y se anota el uso); si no, segundos que faltan."""
        ahora = self.reloj()
        q = self._usos.setdefault(clave, deque())
        while q and ahora - q[0] >= self.ventana:
            q.popleft()
        if len(q) >= self.n:
            return int(self.ventana - (ahora - q[0])) + 1
        q.append(ahora)
        return 0


limite_stt = Limitador(int(os.environ.get("ARIA_VOZ_STT_MINUTO", "12")), 60)
limite_stt_hora = Limitador(int(os.environ.get("ARIA_VOZ_STT_HORA", "200")), 3600)
limite_tts = Limitador(int(os.environ.get("ARIA_VOZ_TTS_MINUTO", "60")), 60)


def limitar_stt(uid) -> int:
    return limite_stt.esperar(uid) or limite_stt_hora.esperar(uid)


# --- Transcripción: Groq y, si falla, local ----------------------------------------------------
_espera_groq = 0.0  # instante hasta el que no se usa Groq (cuota, clave rechazada, caída)
_ahora = time.time


def _cliente(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5))


def groq_disponible() -> bool:
    return bool(os.environ.get("GROQ_API_KEY")) and _ahora() >= _espera_groq


def _anotar_fallo_groq(e: cerebros.ProveedorError) -> None:
    global _espera_groq
    espera = {"cuota": e.espera or 60, "clave": 30 * 60, "modelo": 30 * 60}.get(e.tipo, 30)
    _espera_groq = _ahora() + min(max(espera, 5), 3600)
    log.warning("Groq STT falló (%s); se usa la transcripción local %d s", e.tipo, espera)


async def _groq(datos: bytes, ext: str, mime: str) -> str:
    modelo = os.environ.get("ARIA_STT_GROQ_MODELO") or GROQ_MODELO_DEFECTO
    try:
        async with _cliente(20) as c:
            r = await c.post(GROQ_URL, headers={"Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}"},
                             files={"file": (f"audio.{ext}", datos, mime)},
                             data={"model": modelo, "language": "es", "response_format": "json", "temperature": "0"})
    except httpx.HTTPError as e:
        raise cerebros._error_httpx(e) from None
    if r.status_code != 200:
        raise cerebros.clasificar_http(r.status_code, r.headers, r.text[:2000])
    try:
        texto = r.json().get("text", "")
    except ValueError:
        raise cerebros.ProveedorError("http", "respuesta no válida") from None
    return texto if isinstance(texto, str) else ""


async def _local(datos: bytes, mime: str) -> str:
    try:
        async with _cliente(90) as c:
            r = await c.post(f"{VOZ_URL}/stt", content=datos, headers={"Content-Type": mime})
    except httpx.HTTPError as e:
        raise AudioError(503, "El servicio de voz local no responde.") from e
    if r.status_code == 400:
        raise AudioError(400, "No se pudo leer el audio (¿demasiado largo o dañado?).")
    if r.status_code != 200:
        raise AudioError(503, "El servicio de voz local falló.")
    return str(r.json().get("texto", ""))


async def transcribir(datos: bytes, ext: str, mime: str) -> dict:
    """Groq primero (si hay clave y no está en espera); si falla, aria-voz. No guarda nada."""
    t = time.perf_counter()
    if groq_disponible():
        try:
            texto = await _groq(datos, ext, mime)
            return {"texto": texto.strip(), "proveedor": "groq", "ms": round((time.perf_counter() - t) * 1000)}
        except cerebros.ProveedorError as e:
            _anotar_fallo_groq(e)
    texto = await _local(datos, mime)
    return {"texto": texto.strip(), "proveedor": "local", "ms": round((time.perf_counter() - t) * 1000)}


_PREFIJO_DESPERTAR = re.compile(r"^[\s,.:;!¡-]*(?:(?:oye|hey|ey|eh|hola)[\s,]+)?(?:aria|arya)\b[\s,.:;!-]*", re.I)


def quitar_despertar(texto: str) -> str:
    """Quita un «Aria» inicial (la palabra de activación) que se haya colado en la transcripción."""
    return _PREFIJO_DESPERTAR.sub("", texto.strip(), count=1).strip()


# --- Texto para leer en voz alta ---------------------------------------------------------------
def limpiar_para_voz(texto: str, maximo: int = MAX_TTS_TOTAL) -> str:
    """Quita Markdown, enlaces, código y emojis; recorta en un final de frase."""
    t = texto or ""
    t = re.sub(r"```.*?(```|$)", " ", t, flags=re.S)                  # bloques de código
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)                        # imágenes
    t = re.sub(r"\[([^\]]+)\]\((?:https?:|mailto:)[^)]*\)", r"\1", t)  # [texto](url) -> texto
    t = re.sub(r"<?(?:https?://|www\.)\S+>?", " ", t)                  # URLs sueltas fuera
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)                # títulos
    t = re.sub(r"^\s*>\s?", "", t, flags=re.M)                         # citas
    t = re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s+", "", t, flags=re.M)        # viñetas
    t = re.sub(r"^\s*\|?\s*:?-{2,}.*$", "", t, flags=re.M)             # separadores de tablas
    t = re.sub(r"^[ \t]*\|(.*?)\|?[ \t]*$", r"\1", t, flags=re.M)        # bordes de tablas
    t = re.sub(r"[ \t]*\|[ \t]*", ", ", t)
    t = re.sub(r"(\*\*|__)(.+?)\1", r"\2", t)
    t = re.sub(r"(?<![\w*])[*_]([^*_\n]+)[*_](?![\w*])", r"\1", t)
    t = re.sub(r"~~(.+?)~~", r"\1", t)
    t = re.sub(r"<[^>\n]{1,40}>", " ", t)                              # etiquetas HTML sueltas
    # Emojis y pictogramas fuera (°, €, ·... se quedan: están por debajo de U+2100).
    t = "".join(c for c in t if c not in "\u200d\ufe0f"
                and not (ord(c) >= 0x2100 and unicodedata.category(c) in ("So", "Sk", "Cs", "Co", "Cn")))
    t = re.sub(r"[*#`~]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    if len(t) > maximo:
        corte = t[:maximo]
        fin = max(corte.rfind(". "), corte.rfind("? "), corte.rfind("! "), corte.rfind("\n"))
        t = (corte[:fin + 1] if fin > maximo // 2 else corte.rsplit(" ", 1)[0]).strip()
    return t


def velocidad(v) -> float:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return 1.0
    return min(max(float(v), VEL_MIN), VEL_MAX)


async def sintetizar(texto: str, vel: float) -> bytes:
    try:
        async with _cliente(60) as c:
            r = await c.post(f"{VOZ_URL}/tts", json={"texto": texto, "velocidad": vel})
    except httpx.HTTPError as e:
        raise AudioError(503, "El servicio de voz no responde.") from e
    if r.status_code != 200 or r.headers.get("content-type", "").split(";")[0] != "audio/wav":
        raise AudioError(503, "El servicio de voz falló.")
    return r.content


async def voz_local_ok() -> bool:
    try:
        async with _cliente(3) as c:
            return (await c.get(f"{VOZ_URL}/health")).status_code == 200
    except httpx.HTTPError:
        return False


# --- WebSocket «manos libres» ------------------------------------------------------------------
MAX_TRAMA = 16000           # bytes por mensaje del navegador (0,5 s de PCM a 16 kHz)
MAX_ESCUCHA_S = 3600        # una escucha se corta a la hora (el navegador puede reabrirla)
_escuchas: dict = {}        # uid -> número de escuchas abiertas


def origen_ws_permitido(origin: str | None, host: str | None) -> bool:
    """En WebSocket no hay CORS: el Origin es obligatorio y debe ser el propio host."""
    if not origin or origin == "null" or not host:
        return False
    u = urlparse(origin)
    return u.scheme in ("https", "http") and u.netloc.lower() == host.lower()


def ws_url() -> str:
    return VOZ_URL.replace("http://", "ws://", 1).replace("https://", "wss://", 1) + "/despertar"


_EVENTOS_INTERNOS = {"listo", "despierta", "nada"}


async def retransmitir(ws, uid) -> None:
    """Puente navegador <-> aria-voz. Lo que dice el usuario tras «Aria» llega de aria-voz
    como WAV, se transcribe con la misma cadena (Groq → local) y solo se devuelve el texto."""
    import asyncio
    import json

    from websockets.asyncio.client import connect
    from websockets.exceptions import InvalidStatus, WebSocketException

    try:
        async with connect(ws_url(), max_size=2 ** 21, open_timeout=10, ping_interval=None) as interno:
            async def subir():
                while True:
                    m = await ws.receive()
                    if m["type"] == "websocket.disconnect":
                        return
                    b = m.get("bytes")
                    if b is not None:
                        if len(b) > MAX_TRAMA:
                            return
                        await interno.send(b)
                    elif m.get("text") == '{"type":"reiniciar"}':
                        await interno.send(m["text"])

            async def bajar():
                async for m in interno:
                    if isinstance(m, bytes):
                        await ws.send_json({"type": "procesando"})
                        if (resto := limitar_stt(uid)):
                            await ws.send_json({"type": "error", "text": f"Demasiadas transcripciones seguidas. Espera {resto} s."})
                            continue
                        try:
                            r = await transcribir(m, "wav", "audio/wav")
                        except AudioError as e:
                            await ws.send_json({"type": "error", "text": e.mensaje})
                            continue
                        finally:
                            del m
                        await ws.send_json({"type": "texto", "text": quitar_despertar(r["texto"]),
                                            "proveedor": r["proveedor"], "ms": r["ms"]})
                    else:
                        try:
                            ev = json.loads(m)
                        except ValueError:
                            continue
                        if isinstance(ev, dict) and ev.get("type") in _EVENTOS_INTERNOS:
                            await ws.send_json({"type": ev["type"]})

            tareas = [asyncio.create_task(subir()), asyncio.create_task(bajar())]
            try:
                await asyncio.wait(tareas, timeout=MAX_ESCUCHA_S, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for t in tareas:
                    t.cancel()
                await asyncio.gather(*tareas, return_exceptions=True)
    except InvalidStatus:
        await _enviar_y_cerrar(ws, "El servicio de voz está ocupado con otra escucha. Prueba en un momento.")
        return
    except (OSError, asyncio.TimeoutError, WebSocketException):
        await _enviar_y_cerrar(ws, "El servicio de voz no está disponible.")
        return
    await _enviar_y_cerrar(ws, None)


async def _enviar_y_cerrar(ws, error: str | None) -> None:
    try:
        if error:
            await ws.send_json({"type": "error", "text": error})
        await ws.close()
    except Exception:  # el navegador ya se fue
        pass
