"""Servicio interno para listar y descargar grabaciones de cámaras Tapo."""
import asyncio
import datetime as dt
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Route

CACHE = Path(os.environ.get("ARIA_GRABACIONES_CACHE", "/cache"))
PASSWORD = os.environ.get("ARIA_TAPO_PASSWORD", "")
CAMARAS = [x.strip() for x in os.environ.get("ARIA_TAPO_CAMARAS", "").split(",") if x.strip()]
CACHE_MAX_BYTES = 2 * 1024**3
_candados = {f"c{i}": asyncio.Lock() for i in range(1, len(CAMARAS) + 1)}


def camara(nombre: str):
    if nombre not in _candados or not PASSWORD:
        raise HTTPException(404, "Cámara no encontrada.")
    return nombre, CAMARAS[int(nombre[1:]) - 1]


def _cliente(ip):
    from pytapo import Tapo
    return Tapo(ip, "admin", PASSWORD, PASSWORD, printWarnInformation=False)


def _valor(registro, prefijo):
    return next(iter(v for k, v in registro.items() if k.startswith(prefijo)), {})


async def _dias_y_cliente(nombre):
    _, ip = camara(nombre)
    cliente = await run_in_threadpool(_cliente, ip)
    datos = await run_in_threadpool(cliente.getRecordingsList)
    dias = []
    for registro in datos or []:
        valor = _valor(registro, "search_results_")
        fecha = str(valor.get("date", ""))
        if len(fecha) == 8 and fecha.isdigit():
            dias.append(f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:]}")
    return sorted(set(dias), reverse=True), cliente


async def dias(request):
    nombre = request.query_params.get("cam", "")
    try:
        resultado, _ = await asyncio.wait_for(_dias_y_cliente(nombre), 30)
        return JSONResponse({"dias": resultado})
    except asyncio.TimeoutError:
        return JSONResponse({"error": "La cámara ha tardado demasiado en responder."}, 504)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, e.status_code)
    except Exception:
        return JSONResponse({"error": "No se han podido consultar las grabaciones."}, 502)


def _dia_api(dia):
    try:
        fecha = dt.date.fromisoformat(dia)
    except (TypeError, ValueError):
        raise HTTPException(400, "Día no válido.")
    return fecha.strftime("%Y%m%d")


async def _fragmentos(nombre, dia, cliente=None):
    codigo = _dia_api(dia)
    if cliente is None:
        _, cliente = await _dias_y_cliente(nombre)
    datos = await run_in_threadpool(cliente.getRecordings, codigo)
    resultado = []
    for registro in datos or []:
        valor = _valor(registro, "search_video_results_")
        try:
            inicio, fin, tipo = int(valor["startTime"]), int(valor["endTime"]), int(valor.get("vedio_type", 0))
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= inicio < fin:
            resultado.append({"inicio": inicio, "fin": fin, "tipo": tipo})
    return sorted(resultado, key=lambda x: (x["inicio"], x["fin"]))


async def fragmentos(request):
    try:
        nombre, _ = camara(request.query_params.get("cam", ""))

        async def consultar():
            _, cliente = await _dias_y_cliente(nombre)
            return await _fragmentos(nombre, request.query_params.get("dia", ""), cliente)

        resultado = await asyncio.wait_for(consultar(), 30)
        return JSONResponse({"fragmentos": resultado})
    except asyncio.TimeoutError:
        return JSONResponse({"error": "La cámara ha tardado demasiado en responder."}, 504)
    except HTTPException as e:
        return JSONResponse({"error": e.detail}, e.status_code)
    except Exception:
        return JSONResponse({"error": "No se han podido consultar los fragmentos."}, 502)


def _numero(valor, nombre):
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{nombre} no válido.")
    if n < 0:
        raise HTTPException(400, f"{nombre} no válido.")
    return n


def _clave(nombre, inicio, fin):
    return hashlib.sha256(f"{nombre}:{inicio}:{fin}".encode()).hexdigest()


def _recortar_cache():
    CACHE.mkdir(parents=True, exist_ok=True)
    archivos = [p for p in CACHE.glob("*.mp4") if p.is_file()]
    total = sum(p.stat().st_size for p in archivos)
    for archivo in sorted(archivos, key=lambda p: p.stat().st_atime):
        if total <= CACHE_MAX_BYTES:
            break
        tamano = archivo.stat().st_size
        archivo.unlink(missing_ok=True)
        total -= tamano


async def clip(request):
    nombre, ip = camara(request.query_params.get("cam", ""))
    inicio = _numero(request.query_params.get("inicio"), "Inicio")
    fin = _numero(request.query_params.get("fin"), "Fin")
    if fin <= inicio or fin - inicio > 600:
        return JSONResponse({"error": "La duración debe ser de entre un segundo y diez minutos."}, 400)
    dia = request.query_params.get("dia", "")
    destino = CACHE / f"{_clave(nombre, inicio, fin)}.mp4"
    if destino.exists():   # ya preparado: ni se despierta a la cámara
        return FileResponse(destino, media_type="video/mp4", filename=f"{nombre}-{inicio}.mp4",
                            headers={"Cache-Control": "no-store", "Accept-Ranges": "bytes"})
    candado = _candados[nombre]
    if candado.locked():
        return JSONResponse({"error": "La cámara ya está preparando otra grabación."}, 409)
    async with candado:
        try:
            # Solo se piden fragmentos que existen, y solo se mira el día indicado (mirar todos los días eran
            # decenas de consultas a la cámara por cada clip).
            _, cliente = await run_in_threadpool(lambda: (None, _cliente(ip)))
            valido = any(x["inicio"] == inicio and x["fin"] == fin for x in await _fragmentos(nombre, dia, cliente))
            if not valido:
                return JSONResponse({"error": "El fragmento no existe."}, 404)
            CACHE.mkdir(parents=True, exist_ok=True)
            if not destino.exists():
                tz = await run_in_threadpool(cliente.getTimeCorrection)
                from pytapo.media_stream.downloader import Downloader
                with tempfile.TemporaryDirectory() as temporal:
                    descargador = Downloader(cliente, inicio, fin, tz, outputDirectory=temporal,
                                             output="ts", overwriteFiles=True)
                    await asyncio.wait_for(_descargar(descargador), 120)
                    entrada = next(Path(temporal).glob("*.ts"), None)
                    if entrada is None:
                        raise RuntimeError("La cámara no ha enviado el vídeo.")
                    temporal_mp4 = Path(temporal) / "clip.mp4"
                    proceso = await asyncio.create_subprocess_exec(
                        "ffmpeg", "-y", "-i", str(entrada), "-c:v", "copy", "-c:a", "aac",
                        "-movflags", "+faststart", str(temporal_mp4),
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                    try:
                        await asyncio.wait_for(proceso.communicate(), 120)
                    except asyncio.TimeoutError:
                        proceso.kill()
                        await proceso.wait()
                        raise
                    if proceso.returncode:
                        raise RuntimeError("No se ha podido preparar el vídeo.")
                    shutil.copyfile(temporal_mp4, destino)
                _recortar_cache()
            return FileResponse(destino, media_type="video/mp4", filename=f"{nombre}-{inicio}.mp4",
                                headers={"Cache-Control": "no-store", "Accept-Ranges": "bytes"})
        except asyncio.TimeoutError:
            return JSONResponse({"error": "La cámara ha tardado demasiado en preparar el vídeo."}, 504)
        except HTTPException as e:
            return JSONResponse({"error": e.detail}, e.status_code)
        except Exception:
            return JSONResponse({"error": "No se ha podido preparar el vídeo."}, 502)


async def _descargar(descargador):
    async for _ in descargador.download():
        pass


app = Starlette(routes=[
    Route("/dias", dias),
    Route("/fragmentos", fragmentos),
    Route("/clip", clip),
])
