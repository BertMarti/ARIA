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
from contextlib import closing
from pathlib import Path
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


# Frases que Whisper «se inventa» cuando el audio es casi silencio (lo típico en un PC con el micrófono bajo)
_ALUCINACIONES = {"gracias", "muchas gracias", "gracias por ver", "gracias por ver el video", "gracias por ver el vídeo",
                  "subtitulos realizados por la comunidad de amaraorg", "subtítulos realizados por la comunidad de amaraorg",
                  "suscribete", "suscríbete", "música", "musica", "aplausos", "risas", "adiós", "hasta luego", "chao", "you", "thank you"}


def _nivel_wav(datos: bytes) -> float:
    """RMS (0..1) del PCM 16 bits de un WAV con cabecera de 44 bytes."""
    pcm = memoryview(datos)[44:]
    n = len(pcm) // 2
    if not n:
        return 0.0
    muestras = pcm[: n * 2].cast("h")
    paso = max(1, n // 4000)   # basta una muestra de cada pocas para estimar el nivel
    vals = muestras[::paso]
    return (sum(v * v for v in vals) / len(vals)) ** .5 / 32768


def es_alucinacion(texto: str, datos: bytes | None = None) -> bool:
    """True si la transcripción es una muletilla típica de Whisper sobre audio casi mudo (o está vacía)."""
    t = re.sub(r"[^\w\s]", "", (texto or "").lower()).strip()
    t = " ".join(t.split())
    if not t:
        return True
    if t in _ALUCINACIONES:
        return True
    return datos is not None and len(t) < 12 and _nivel_wav(datos) < .004


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
# La capa gratuita da 3 peticiones/minuto POR MODELO: se rota entre varios modelos TTS con la misma voz.
# «:plano» = ese modelo lee en voz alta las indicaciones de estilo, así que solo recibe el texto.
GEMINI_TTS_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
TTS_MODELOS = [m.strip() for m in os.environ.get(
    "ARIA_TTS_MODELOS", "gemini-3.1-flash-tts-preview,gemini-2.5-flash-preview-tts,gemini-3.8-flash-tts:plano"
).split(",") if m.strip()]
TTS_VOZ = os.environ.get("ARIA_TTS_VOZ", "Leda")

# Voces femeninas de Gemini, con su carácter (según Google), y cómo se le pide a Gemini que hable.
VOCES = {
    "Leda": "Juvenil y cálida", "Achernar": "Suave y delicada", "Vindemiatrix": "Amable y tierna",
    "Sulafat": "Cálida y cercana", "Despina": "Aterciopelada", "Aoede": "Ligera y alegre",
    "Callirrhoe": "Tranquila y relajada", "Autonoe": "Luminosa", "Laomedeia": "Animada y risueña",
    "Erinome": "Clara y nítida", "Zephyr": "Brillante", "Kore": "Firme y segura",
    "Gacrux": "Madura y serena", "Pulcherrima": "Directa y expresiva",
}
TONOS = {
    "dulce": ("Dulce y cariñosa", "con una voz femenina muy dulce, cálida y cariñosa, sonriendo"),
    "alegre": ("Alegre", "con una voz femenina alegre, cercana y llena de energía"),
    "serena": ("Serena", "con una voz femenina serena y suave, con calma y sin prisa"),
    "tierna": ("Muy tierna", "con una voz femenina muy tierna y delicada, casi susurrando con cariño"),
}
ACENTOS = {"es-ES": ("España", "con acento de España (castellano peninsular)"),
           "es-US": ("Latinoamérica", "con acento latinoamericano neutro")}
PREF_DEFECTO = {"voz": TTS_VOZ if TTS_VOZ in VOCES else "Leda", "tono": "dulce", "acento": "es-ES"}
FRASE_MUESTRA = "Hola, soy ARIA. Estoy aquí para ayudarte en lo que necesites. ¿Qué tal te ha ido el día?"


PROPIA = "propia"   # voz entrenada en casa (herramientas/voz-propia), servida por aria-voz sin internet


def preferencia(datos: dict | None) -> dict:
    """Normaliza una preferencia de voz (valores desconocidos -> los de por defecto)."""
    d = dict(PREF_DEFECTO)
    for k, validos in (("voz", {**VOCES, PROPIA: ""}), ("tono", TONOS), ("acento", ACENTOS)):
        if isinstance(datos, dict) and datos.get(k) in validos:
            d[k] = datos[k]
    return d
_espera_gemini: dict = {}  # modelo -> instante hasta el que no se usa (cuota, error)
_cache_tts: OrderedDict = OrderedDict()  # (texto, velocidad) -> WAV; ahorra cuota al releer
CACHE_TTS = 64


def _modelos_libres() -> list:
    ahora = _ahora()
    return [m for m in TTS_MODELOS if _espera_gemini.get(m.split(":")[0], 0) <= ahora]


def gemini_tts_disponible() -> bool:
    return (os.environ.get("ARIA_TTS", "gemini").lower() == "gemini" and bool(os.environ.get("GEMINI_API_KEY"))
            and bool(_modelos_libres()))


def _anotar_fallo_gemini(modelo: str, espera: float, motivo: str) -> None:
    # Un 429 trae cuánto falta para la nueva cuota (la diaria se renueva a las 9:00 en España): se respeta entera
    _espera_gemini[modelo] = _ahora() + min(max(espera, 5), 86400 if motivo == "HTTP 429" else 3600)
    log.warning("Gemini TTS %s falló (%s); en espera %d s", modelo, motivo, espera)


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


def _estilo(vel: float, pref: dict | None = None) -> str:
    """Indicación para Gemini, en español, para que no elija otro acento. El texto va después de los dos puntos."""
    p = preferencia(pref)
    ritmo = ", un poco más deprisa" if vel >= 1.15 else ", despacio" if vel <= 0.85 else ""
    return f"Lee en español {ACENTOS[p['acento']][1]}, {TONOS[p['tono']][1]}{ritmo}: "


def _espera_429(r: httpx.Response) -> float:
    if (ra := r.headers.get("retry-after", "")).isdigit():
        return float(ra)
    m = re.search(r'"retryDelay":\s*"(\d+)', r.text)
    return float(m.group(1)) + 1 if m else 60


async def _gemini_modelo(modelo: str, plano: bool, texto: str, vel: float, pref: dict | None = None) -> bytes:
    import base64
    p = preferencia(pref)
    cuerpo = {"contents": [{"parts": [{"text": texto if plano else _estilo(vel, p) + texto}]}],
              "generationConfig": {"responseModalities": ["AUDIO"],
                                   "speechConfig": {"languageCode": p["acento"],
                                                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": p["voz"]}}}}}
    try:
        async with _cliente(30) as c:
            r = await c.post(GEMINI_TTS_URL.format(modelo), json=cuerpo,
                             headers={"x-goog-api-key": os.environ.get("GEMINI_API_KEY", "")})
    except httpx.HTTPError as e:
        _anotar_fallo_gemini(modelo, 30, "red")
        raise AudioError(503, "Gemini no responde.") from e
    if r.status_code != 200:
        espera = _espera_429(r) if r.status_code == 429 else 1800 if r.status_code in (400, 401, 403, 404) else 30
        _anotar_fallo_gemini(modelo, espera, f"HTTP {r.status_code}")
        raise AudioError(503, "Gemini falló.")
    try:
        parte = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        datos = base64.b64decode(parte["data"])
    except (KeyError, IndexError, TypeError, ValueError) as e:
        _anotar_fallo_gemini(modelo, 30, "respuesta sin audio")
        raise AudioError(503, "Gemini no devolvió audio.") from e
    if datos[:4] != b"RIFF":  # PCM 16 bits mono, p. ej. «audio/L16;codec=pcm;rate=24000»
        m = re.search(r"rate=(\d+)", parte.get("mimeType", ""))
        datos = _pcm_a_wav(datos, int(m.group(1)) if m else 24000)
    dur = duracion_wav(datos) or 0
    # Si el modelo lee también las indicaciones o se repite, el audio sale demasiado largo
    if not (0.02 * len(texto) <= dur <= 0.1 * len(texto) / vel + 2):
        _anotar_fallo_gemini(modelo, 600, f"{dur:.1f} s para {len(texto)} caracteres")
        raise AudioError(503, "Audio de Gemini dudoso.")
    return datos


async def _gemini(texto: str, vel: float, pref: dict | None = None) -> bytes:
    for m in _modelos_libres():
        modelo, _, opcion = m.partition(":")
        try:
            return await _gemini_modelo(modelo, opcion == "plano", texto, vel, pref)
        except AudioError:
            continue
    raise AudioError(503, "Ningún modelo de voz de Gemini disponible.")


async def sintetizar(texto: str, vel: float, pref: dict | None = None) -> bytes:
    return (await sintetizar_info(texto, vel, pref))[0]


def gemini_vuelve() -> float | None:
    """Instante (epoch) en que vuelve a haber algún modelo de voz de Gemini, o None si ya lo hay."""
    if _modelos_libres():
        return None
    esperas = [_espera_gemini.get(m.split(":")[0], 0) for m in TTS_MODELOS]
    return time.time() + max(0, min(esperas) - _ahora()) if esperas else None


async def sintetizar_info(texto: str, vel: float, pref: dict | None = None) -> tuple[bytes, str]:
    """(wav, motor): «gemini» con la voz elegida por el usuario si hay clave y cuota; si no, «local» (Piper)."""
    p = preferencia(pref)
    if p["voz"] == PROPIA:   # la voz propia vive en la Raspberry: ni cuota ni internet
        return await sintetizar_local(texto, vel, PROPIA), PROPIA
    clave = (texto, round(vel, 2), p["voz"], p["tono"], p["acento"])
    if clave in _cache_tts:
        _cache_tts.move_to_end(clave)
        return _cache_tts[clave], "gemini"
    if gemini_tts_disponible():
        try:
            wav = await _gemini(texto, vel, p)
            _cache_tts[clave] = wav
            if len(_cache_tts) > CACHE_TTS:
                _cache_tts.popitem(last=False)
            return wav, "gemini"
        except AudioError:
            pass
    return await sintetizar_local(texto, vel), "local"


async def sintetizar_local(texto: str, vel: float, voz: str = "auto") -> bytes:
    """Piper en aria-voz. «auto» usa la voz propia si está instalada; si no, la de base."""
    try:
        async with _cliente(60) as c:
            r = await c.post(f"{VOZ_URL}/tts", json={"texto": texto, "velocidad": vel, "voz": voz})
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
                            texto = quitar_despertar(r["texto"])
                            dudoso = es_alucinacion(texto, m)
                        except AudioError as e:
                            await ws.send_json({"type": "error", "text": e.mensaje})
                            continue
                        finally:
                            del m
                        if dudoso:
                            await ws.send_json({"type": "texto", "text": "", "aviso": "No te he oído bien: habla un poco más alto o "
                                                "más cerca, o revisa el micrófono en Ajustes → Voz."})
                            continue
                        await ws.send_json({"type": "texto", "text": texto, "proveedor": r["proveedor"], "ms": r["ms"]})
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


# --- Preferencias de voz por usuario y muestras para probar las voces -------------------------------
def iniciar() -> None:
    from . import db
    with closing(db._con()) as con, con:
        con.execute("CREATE TABLE IF NOT EXISTS voz_preferencias (user_id INTEGER PRIMARY KEY REFERENCES usuarios(id) "
                    "ON DELETE CASCADE, voz TEXT NOT NULL, tono TEXT NOT NULL, acento TEXT NOT NULL)")


def preferencias_de(uid: int) -> dict:
    from . import db
    with closing(db._con()) as con:
        r = con.execute("SELECT voz, tono, acento FROM voz_preferencias WHERE user_id=?", (uid,)).fetchone()
    return preferencia(dict(r) if r else None)


def guardar_preferencias(uid: int, datos: dict) -> dict:
    from . import db
    p = preferencia({**preferencias_de(uid), **{k: v for k, v in (datos or {}).items() if k in ("voz", "tono", "acento")}})
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO voz_preferencias (user_id, voz, tono, acento) VALUES (?,?,?,?) ON CONFLICT(user_id) "
                    "DO UPDATE SET voz=excluded.voz, tono=excluded.tono, acento=excluded.acento",
                    (uid, p["voz"], p["tono"], p["acento"]))
    return p


def _ruta_muestra(p: dict) -> Path:
    from . import config
    return config.DATA_DIR / "voz-muestras" / f"{p['voz']}-{p['tono']}-{p['acento']}.wav"


_propia_cache: dict = {}


async def voz_propia() -> str | None:
    """Nombre de la voz propia instalada en aria-voz (o None). Se consulta como mucho una vez por minuto."""
    if _propia_cache and _ahora() - _propia_cache["t"] < 60:
        return _propia_cache["nombre"]
    nombre = None
    try:
        async with _cliente(5) as c:
            r = await c.get(f"{VOZ_URL}/estado")
        if r.status_code == 200:
            nombre = r.json().get("propia")
    except (httpx.HTTPError, ValueError):
        pass
    _propia_cache.update(t=_ahora(), nombre=nombre)
    return nombre


async def muestra(pref: dict) -> bytes:
    """Frase de prueba con esa voz. Se guarda en disco: cada combinación gasta cuota de Gemini una sola vez."""
    p = preferencia(pref)
    if p["voz"] == PROPIA:
        return await sintetizar_local(FRASE_MUESTRA, 1.0, PROPIA)
    ruta = _ruta_muestra(p)
    if ruta.exists():
        return ruta.read_bytes()
    if not gemini_tts_disponible():
        raise AudioError(503, "Las voces de Gemini no están disponibles ahora (falta la clave o se agotó la cuota "
                              "del minuto). Inténtalo en un momento.")
    wav = await _gemini(FRASE_MUESTRA, 1.0, p)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_bytes(wav)
    tmp.replace(ruta)
    return wav
