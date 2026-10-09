"""aria-voz: transcripción local (faster-whisper), síntesis de voz (Piper) y palabra de
activación «Aria» (Vosk con gramática cerrada).

Solo lo usa aria-app por una red interna de Docker: no publica puertos ni tiene salida a
Internet. El audio se procesa en memoria y nunca se guarda en disco.
"""
import asyncio
import io
import json
import logging
import os
import threading
import time
import wave
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse, Response

log = logging.getLogger("uvicorn.error")

MODELOS = Path(os.environ.get("VOZ_MODELOS", "/modelos"))
WHISPER = os.environ.get("VOZ_WHISPER", "base")
VOZ_PIPER = os.environ.get("VOZ_PIPER", "es_ES-sharvard-medium")
HABLANTE = os.environ.get("VOZ_HABLANTE", "F")  # sharvard trae voz «M» y «F»: ARIA habla con voz femenina
HILOS = int(os.environ.get("VOZ_HILOS", "4"))
MAX_FLUJOS = int(os.environ.get("VOZ_MAX_FLUJOS", "2"))     # escuchas «manos libres» simultáneas
INACTIVO_S = int(os.environ.get("VOZ_INACTIVO_S", "600"))   # libera Whisper tras este tiempo sin uso

MAX_BYTES = 2_000_000
MAX_AUDIO_S = 60
MAX_TEXTO = 1000
SR = 16000

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# --- Whisper (bajo demanda; se libera si no se usa) -------------------------------------
_whisper = None
_whisper_uso = 0.0
_cerrojo_whisper = threading.Lock()
_cerrojo_piper = threading.Lock()
_piper = None
_flujos = 0


def _modelo_whisper():
    global _whisper, _whisper_uso
    from faster_whisper import WhisperModel
    if _whisper is None:
        t = time.perf_counter()
        _whisper = WhisperModel(str(MODELOS / "whisper" / WHISPER), device="cpu",
                                compute_type="int8", cpu_threads=HILOS)
        log.info("Whisper %s cargado en %.1f s", WHISPER, time.perf_counter() - t)
    _whisper_uso = time.time()
    return _whisper


def transcribir(datos: bytes) -> dict:
    from faster_whisper.audio import decode_audio
    try:
        audio = decode_audio(io.BytesIO(datos), sampling_rate=SR)
    except Exception as e:  # PyAV lanza varios tipos
        raise ValueError("audio no válido") from e
    duracion = len(audio) / SR
    if duracion > MAX_AUDIO_S:
        raise ValueError("audio demasiado largo")
    if duracion < 0.2:
        return {"texto": "", "duracion": duracion}
    t = time.perf_counter()
    with _cerrojo_whisper:  # uno a la vez: la Pi tiene 4 núcleos y el LLM también los usa
        segs, _ = _modelo_whisper().transcribe(audio, language="es", beam_size=1, vad_filter=True,
                                               condition_on_previous_text=False)
        texto = " ".join(s.text.strip() for s in segs).strip()
    return {"texto": texto, "duracion": round(duracion, 2), "ms": round((time.perf_counter() - t) * 1000)}


async def _liberar_whisper():
    global _whisper
    while True:
        await asyncio.sleep(60)
        if _whisper is not None and time.time() - _whisper_uso > INACTIVO_S:
            with _cerrojo_whisper:
                _whisper = None
            log.info("Whisper liberado por inactividad")


# --- Piper ---------------------------------------------------------------------------------
def _voz():
    global _piper
    from piper import PiperVoice
    if _piper is None:
        _piper = PiperVoice.load(str(MODELOS / "piper" / f"{VOZ_PIPER}.onnx"))
    return _piper


# Voz propia (entrenada con herramientas/voz-propia): el primer .onnx de VOZ_PROPIA_DIR con su .onnx.json.
# Si existe, es la voz local por defecto; se recarga sola si cambias el archivo.
PROPIA_DIR = Path(os.environ.get("VOZ_PROPIA_DIR", "/voz-propia"))
_propia: dict = {}


def _ruta_propia() -> Path | None:
    try:
        return next((p for p in sorted(PROPIA_DIR.glob("*.onnx")) if p.with_suffix(".onnx.json").exists()), None)
    except OSError:
        return None


def _voz_propia():
    from piper import PiperVoice
    ruta = _ruta_propia()
    if ruta is None:
        return None
    clave = (str(ruta), ruta.stat().st_mtime)
    if _propia.get("clave") != clave:
        _propia.update(clave=clave, voz=PiperVoice.load(str(ruta)), nombre=ruta.stem)
        log.info("Voz propia cargada: %s", ruta.name)
    return _propia["voz"]


def sintetizar(texto: str, velocidad: float, voz: str = "auto") -> bytes:
    """voz: «propia», «base» (sharvard) o «auto» (la propia si está instalada)."""
    from piper import SynthesisConfig
    v = None
    if voz in ("auto", "propia"):
        try:
            v = _voz_propia()
        except Exception:  # noqa: BLE001 - un modelo propio roto no debe dejar a ARIA sin voz
            log.exception("No se pudo cargar la voz propia; se usa la de base")
    if v is None:
        v = _voz()
    mapa = v.config.speaker_id_map or {}
    cfg = SynthesisConfig(length_scale=1.0 / velocidad, speaker_id=mapa.get(HABLANTE) if mapa else None)
    buf = io.BytesIO()
    with _cerrojo_piper:
        with wave.open(buf, "wb") as w:
            v.synthesize_wav(texto, w, syn_config=cfg)
    return buf.getvalue()


def wav_a_ogg(wav: bytes) -> bytes:
    """WAV PCM16 mono -> OGG/Opus (nota de voz de Telegram). PyAV ya viene con faster-whisper."""
    import av
    import numpy as np
    with wave.open(io.BytesIO(wav)) as w:
        sr, canales, pcm = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    muestras = np.frombuffer(pcm, dtype=np.int16).reshape(1, -1)
    salida = io.BytesIO()
    with av.open(salida, "w", format="ogg") as cont:
        flujo = cont.add_stream("libopus", rate=48000)
        flujo.bit_rate = 32000
        flujo.layout = "mono"
        trama = av.AudioFrame.from_ndarray(muestras, format="s16", layout="mono" if canales == 1 else "stereo")
        trama.sample_rate = sr
        for paquete in flujo.encode(trama):
            cont.mux(paquete)
        for paquete in flujo.encode(None):
            cont.mux(paquete)
    return salida.getvalue()


# --- Palabra de activación «Aria» (Vosk con gramática cerrada) ------------------------------
# Vosk solo puede elegir entre estas palabras. Además de «aria» hay palabras «señuelo» que
# suenan parecido (María, Ariadna, varias, amplia...) y palabras cortas frecuentes: así lo que
# no es «Aria» cae en un señuelo en vez de forzarse a «aria». «área» NO es señuelo: Vosk
# confunde con ella el propio «Aria». Medido con frases de Piper: ver MEMORY.md.
PALABRA = "aria"
SENUELOS = ["maría", "mario", "marina", "varias", "ariadna", "amplia", "ópera", "agria", "valeria",
            "daría", "sería", "habría", "una", "la", "el", "de", "me", "que", "qué", "esta", "era",
            "para", "hacia", "ahora", "oye"]
GRAMATICA = json.dumps([PALABRA, "oye aria", *SENUELOS, "[unk]"], ensure_ascii=False)
CONF_MIN = float(os.environ.get("VOZ_CONFIANZA", "0.6"))  # confianza mínima de «aria»
ENFRIAR_S = 2.0          # tras una orden, se ignora «aria» durante este tiempo
ORDEN_ESPERA_S = 6.0     # tras «Aria», tiempo para empezar a hablar
ORDEN_MAX_S = 12.0       # duración máxima de lo que se dice tras «Aria»
SILENCIO_FIN_S = 0.8     # pausa que da la orden por terminada
MARGEN_S = 0.25
MEMORIA_S = 20           # audio reciente que se conserva (solo en RAM) para recortar la orden
VENTANA = 1280           # 80 ms para el detector de voz por energía
_vosk = None
_cerrojo_vosk = threading.Lock()


def _modelo_vosk():
    global _vosk
    with _cerrojo_vosk:
        if _vosk is None:
            import vosk
            vosk.SetLogLevel(-1)
            _vosk = vosk.Model(str(next((MODELOS / "vosk").iterdir())))
    return _vosk


def wav_pcm16(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return buf.getvalue()


def _rms(pcm: bytes) -> float:
    import numpy as np
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(a * a))) if a.size else 0.0


class Escucha:
    """Una escucha «manos libres». Recibe PCM 16 kHz mono int16 y devuelve eventos:
    dicts (JSON para el navegador) o bytes (WAV de lo dicho tras «Aria»).

    «Aria» solo cuenta si es la primera palabra de una frase de Vosk (es decir, tras una pausa)
    y con confianza suficiente: «el aria», «esta aria de ópera» o «María» no la activan. Desde el
    final de «Aria» se guarda lo que se dice hasta una pausa de 0,8 s (detector por energía), sea
    de un tirón («Aria, ¿qué hora es?») o tras una pausa («Aria.» … «¿qué hora es?»)."""

    def __init__(self):
        from vosk import KaldiRecognizer
        self.rec = KaldiRecognizer(_modelo_vosk(), SR, GRAMATICA)
        self.rec.SetWords(True)
        self.total = 0           # muestras recibidas (eje de tiempos de Vosk: Reset() no lo reinicia)
        self.reiniciar()

    def reiniciar(self):
        self.rec.Reset()
        self.pcm = bytearray()   # audio reciente (se recorta a MEMORIA_S)
        self.base = self.total   # muestra absoluta del primer byte de self.pcm
        self.ruido = 200.0       # nivel de fondo estimado (RMS)
        self.enfriar_hasta = 0
        self._sin_orden()

    def _sin_orden(self):
        self.orden_desde = None  # muestra donde empieza la orden
        self.vad_hasta = 0       # hasta dónde se ha analizado la energía
        self.hablo = False
        self.ultima_voz = 0      # última muestra con voz

    def _trozo(self, desde: int, hasta: int) -> bytes:
        return bytes(self.pcm[max(desde - self.base, 0) * 2:max(hasta - self.base, 0) * 2])

    def alimentar(self, datos: bytes) -> list:
        if len(datos) % 2:
            datos = datos[:-1]
        self.pcm += datos
        self.total += len(datos) // 2
        sobra = len(self.pcm) // 2 - MEMORIA_S * SR
        if sobra > 0:
            del self.pcm[:sobra * 2]
            self.base += sobra
        eventos = []
        if self.orden_desde is None:
            nivel = _rms(datos)
            if nivel < self.ruido * 1.5:  # el fondo se adapta solo con lo que no parece voz
                self.ruido = max(50.0, 0.95 * self.ruido + 0.05 * nivel)
        if self.rec.AcceptWaveform(datos) and self.orden_desde is None:
            eventos += self._frase(json.loads(self.rec.Result()))
        if self.orden_desde is not None:
            ev = self._seguir_orden()
            if ev is not None:
                eventos.append(ev)
        return eventos

    def _frase(self, r: dict) -> list:
        palabras = r.get("result") or []
        i = 1 if len(palabras) > 1 and palabras[0]["word"] == "oye" else 0
        if not palabras or palabras[i]["word"] != PALABRA or self.total < self.enfriar_hasta:
            return []
        conf = float(palabras[i].get("conf", 0))
        if conf < CONF_MIN:
            return []
        self.orden_desde = self.vad_hasta = int(palabras[i]["end"] * SR)
        return [{"type": "despierta", "confianza": round(conf, 2)}]

    def _seguir_orden(self):
        umbral = max(self.ruido * 3, 400.0)
        while self.total - self.vad_hasta >= VENTANA:  # también el audio ya pasado tras «Aria»
            fin = self.vad_hasta + VENTANA
            if _rms(self._trozo(self.vad_hasta, fin)) > umbral:
                self.hablo, self.ultima_voz = True, fin
            self.vad_hasta = fin
        pasado = (self.total - self.orden_desde) / SR
        if self.hablo and ((self.total - self.ultima_voz) / SR >= SILENCIO_FIN_S or pasado >= ORDEN_MAX_S):
            audio = self._trozo(self.orden_desde, min(self.ultima_voz + int(MARGEN_S * SR), self.total))
            self._sin_orden()
            self.enfriar_hasta = self.total + int(ENFRIAR_S * SR)
            self.rec.Reset()  # lo dicho en la orden no debe contar como frase nueva
            return wav_pcm16(audio)
        if not self.hablo and pasado >= ORDEN_ESPERA_S:
            self._sin_orden()
            return {"type": "nada"}
        return None


# --- API interna -----------------------------------------------------------------------------
@app.on_event("startup")
async def _arranque():
    asyncio.create_task(_liberar_whisper())


@app.get("/health")
async def health():
    return PlainTextResponse("ok")


@app.get("/estado")
async def estado():
    propia = _ruta_propia()
    return {"whisper": WHISPER, "whisper_cargado": _whisper is not None, "voz": VOZ_PIPER,
            "propia": propia.stem if propia else None,
            "activacion": "aria",
            "flujos": _flujos, "max_flujos": MAX_FLUJOS}


@app.post("/stt")
async def stt(request: Request):
    datos = await request.body()
    if not datos or len(datos) > MAX_BYTES:
        return JSONResponse({"error": "tamaño no válido"}, status_code=413)
    try:
        return await asyncio.to_thread(transcribir, datos)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    finally:
        del datos  # el audio solo vive en memoria durante la petición


@app.post("/tts")
async def tts(request: Request):
    try:
        d = await request.json()
    except ValueError:
        d = {}
    texto = d.get("texto") if isinstance(d, dict) else None
    vel = d.get("velocidad", 1.0) if isinstance(d, dict) else 1.0
    if not isinstance(texto, str) or not texto.strip() or len(texto) > MAX_TEXTO:
        return JSONResponse({"error": "texto no válido"}, status_code=400)
    if not isinstance(vel, (int, float)) or isinstance(vel, bool) or not 0.5 <= vel <= 2.0:
        vel = 1.0
    voz = d.get("voz") if isinstance(d, dict) and d.get("voz") in ("auto", "propia", "base") else "auto"
    wav = await asyncio.to_thread(sintetizar, texto.strip(), float(vel), voz)
    if isinstance(d, dict) and d.get("formato") == "ogg":  # notas de voz de Telegram (OGG/Opus)
        try:
            return Response(await asyncio.to_thread(wav_a_ogg, wav), media_type="audio/ogg")
        except Exception:  # noqa: BLE001 - si falla la conversión, se devuelve el WAV
            log.exception("No se pudo convertir a OGG/Opus")
    return Response(wav, media_type="audio/wav")


@app.post("/ogg")
async def ogg(request: Request):
    """WAV (p. ej. la voz de Gemini que genera la app) -> OGG/Opus para las notas de voz de Telegram."""
    datos = await request.body()
    if len(datos) > 8_000_000 or datos[:4] != b"RIFF" or datos[8:12] != b"WAVE":
        return JSONResponse({"error": "WAV no válido"}, status_code=400)
    try:
        return Response(await asyncio.to_thread(wav_a_ogg, datos), media_type="audio/ogg")
    except Exception:  # noqa: BLE001
        log.exception("No se pudo convertir a OGG/Opus")
        return JSONResponse({"error": "no se pudo convertir"}, status_code=500)


@app.websocket("/despertar")
async def despertar(ws: WebSocket):
    global _flujos
    if _flujos >= MAX_FLUJOS:
        await ws.close(code=1013)  # ocupado
        return
    _flujos += 1
    try:
        await ws.accept()
        escucha = await asyncio.to_thread(Escucha)
        await ws.send_json({"type": "listo"})
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes"):
                for ev in await asyncio.to_thread(escucha.alimentar, msg["bytes"]):
                    if isinstance(ev, bytes):
                        await ws.send_bytes(ev)
                    else:
                        await ws.send_json(ev)
            elif msg.get("text") == '{"type":"reiniciar"}':
                await asyncio.to_thread(escucha.reiniciar)
    except WebSocketDisconnect:
        pass
    finally:
        _flujos -= 1
