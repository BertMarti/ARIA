"""Voz: transcripción (Groq Whisper → aria-voz local), síntesis (Gemini «Leda» → Piper en aria-voz) y
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
from collections import OrderedDict, deque
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


# --- Síntesis: Gemini (voz femenina natural «Leda») y, si falla, Piper en aria-voz -----------------
GEMINI_TTS_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
TTS_MODELO = os.environ.get("ARIA_TTS_MODELO", "gemini-3.8-flash-tts")
TTS_VOZ = os.environ.get("ARIA_TTS_VOZ", "Leda")
TTS_ESTILO = os.environ.get("ARIA_TTS_ESTILO", "Di con voz femenina cálida, dulce, cercana y natural, "
                            "en español de España")
_espera_gemini = 0.0
_cache_tts: OrderedDict = OrderedDict()  # (texto, velocidad) -> WAV; ahorra cuota al releer
CACHE_TTS = 64


def gemini_tts_disponible() -> bool:
    return (os.environ.get("ARIA_TTS", "gemini").lower() == "gemini" and bool(os.environ.get("GEMINI_API_KEY"))
            and _ahora() >= _espera_gemini)


def _anotar_fallo_gemini(espera: float, motivo: str) -> None:
    global _espera_gemini
    _espera_gemini = _ahora() + min(max(espera, 5), 3600)
    log.warning("Gemini TTS falló (%s); se usa la voz local %d s", motivo, espera)


def _pcm_a_wav(pcm: bytes, frecuencia: int = 24000) -> bytes:
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frecuencia)
        w.writeframes(pcm)
    return buf.getvalue()


def _ritmo(vel: float) -> str:
    return " y a ritmo algo rápido" if vel >= 1.15 else " y despacio" if vel <= 0.85 else " y a ritmo tranquilo"


async def _gemini(texto: str, vel: float) -> bytes:
    import base64
    cuerpo = {"contents": [{"parts": [{"text": f"{TTS_ESTILO}{_ritmo(vel)}: {texto}"}]}],
              "generationConfig": {"responseModalities": ["AUDIO"],
                                   "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOZ}}}}}
    try:
        async with _cliente(30) as c:
            r = await c.post(GEMINI_TTS_URL.format(TTS_MODELO), json=cuerpo,
                             headers={"x-goog-api-key": os.environ.get("GEMINI_API_KEY", "")})
    except httpx.HTTPError as e:
        _anotar_fallo_gemini(30, "red")
        raise AudioError(503, "Gemini no responde.") from e
    if r.status_code != 200:
        espera = {429: float(r.headers.get("retry-after") or 120), 400: 1800, 401: 1800, 403: 1800, 404: 1800}
        _anotar_fallo_gemini(espera.get(r.status_code, 30), f"HTTP {r.status_code}")
        raise AudioError(503, "Gemini falló.")
    try:
        parte = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        datos = base64.b64decode(parte["data"])
    except (KeyError, IndexError, TypeError, ValueError) as e:
        _anotar_fallo_gemini(30, "respuesta sin audio")
        raise AudioError(503, "Gemini no devolvió audio.") from e
    if datos[:4] != b"RIFF":  # PCM 16 bits mono, p. ej. «audio/L16;codec=pcm;rate=24000»
        m = re.search(r"rate=(\d+)", parte.get("mimeType", ""))
        datos = _pcm_a_wav(datos, int(m.group(1)) if m else 24000)
    dur = duracion_wav(datos) or 0
    # Si el modelo lee también las instrucciones o se repite, el audio sale demasiado largo: mejor Piper
    if not (0.02 * len(texto) <= dur <= 0.1 * len(texto) / vel + 2):
        log.warning("Gemini TTS devolvió %.1f s para %d caracteres; se usa la voz local", dur, len(texto))
        raise AudioError(503, "Audio de Gemini dudoso.")
    return datos


async def sintetizar(texto: str, vel: float) -> bytes:
    """Gemini (voz «Leda») si hay clave y no está en espera; si no, Piper en aria-voz."""
    clave = (texto, round(vel, 2))
    if clave in _cache_tts:
        _cache_tts.move_to_end(clave)
        return _cache_tts[clave]
    if gemini_tts_disponible():
        try:
            wav = await _gemini(texto, vel)
            _cache_tts[clave] = wav
            if len(_cache_tts) > CACHE_TTS:
                _cache_tts.popitem(last=False)
            return wav
        except AudioError:
            pass
    return await sintetizar_local(texto, vel)


async def sintetizar_local(texto: str, vel: float) -> bytes:
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
