import asyncio
import html
import math
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from . import config, tele

router = APIRouter()


def _json_error(text, code=400):
    return JSONResponse({"error": text}, status_code=code)


def _rango(valor, tamano):
    if not valor:
        return None
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", valor)
    if not m or (not m.group(1) and not m.group(2)):
        raise tele.TeleError("Rango no válido")
    if m.group(1):
        a = int(m.group(1))
        b = int(m.group(2) or tamano - 1)
        if a >= tamano or b < a:
            raise tele.TeleError("Rango fuera de rango")
        return a, min(b, tamano - 1)
    n = int(m.group(2))
    if n <= 0: raise tele.TeleError("Rango fuera de rango")
    return max(0, tamano - n), tamano - 1


@router.api_route("/flujo/{token}/{nombre:path}", methods=["GET", "HEAD"])
async def flujo(token: str, nombre: str, request: Request):
    dato = tele.validar_token(token)
    if not dato:
        return _json_error("No encontrado", 404)
    try:
        rango = _rango(request.headers.get("range"), dato.tamano)
        dato, generador = await tele.flujo(token, rango)
    except tele.TeleError:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{dato.tamano}"})
    inicio, fin = rango or (0, dato.tamano - 1)
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(fin - inicio + 1),
               "Content-Type": dato.mime, "transferMode.dlna.org": "Streaming",
               "contentFeatures.dlna.org": "DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"}
    if rango: headers["Content-Range"] = f"bytes {inicio}-{fin}/{dato.tamano}"
    if request.method == "HEAD": return Response(status_code=206 if rango else 200, headers=headers)
    return StreamingResponse(generador, status_code=206 if rango else 200, headers=headers, media_type=dato.mime)


@router.get("/api/tele/dispositivos")
async def dispositivos():
    return await tele.descubrir()


@router.post("/api/tele/dispositivos")
async def dispositivo(request: Request):
    try:
        d = await request.json()
    except (TypeError, ValueError):
        return _json_error("JSON no válido")
    if not isinstance(d, dict):
        return _json_error("JSON no válido")
    ip = d.get("ip") if isinstance(d, dict) else None
    try: tele._destino(ip)
    except tele.TeleError as e: return _json_error(str(e), 400)
    tipo = d.get("tipo", "dlna")
    if tipo not in ("chromecast", "dlna"):
        return _json_error("Tipo no válido")
    dato = {"id": f"manual:{ip}", "nombre": ip, "tipo": tipo, "ip": ip}
    tele._dispositivos[dato["id"]] = dato
    return dato


async def _dispositivo(identificador):
    if not isinstance(identificador, str):
        return None
    return next((d for d in await tele.descubrir() if d.get("id") == identificador), None)


def _numero(valor, defecto=0.0):
    if valor is None:
        valor = defecto
    if isinstance(valor, bool):
        raise ValueError
    dato = float(valor)
    if not math.isfinite(dato) or dato < 0:
        raise ValueError
    return dato


async def _json(request):
    try:
        dato = await request.json()
    except (TypeError, ValueError):
        return None
    return dato if isinstance(dato, dict) else None


@router.post("/api/tele/enviar")
async def enviar(request: Request):
    d = await _json(request)
    if d is None:
        return _json_error("JSON no válido")
    usuario = request.state.usuario
    dato = tele.validar_token(d.get("token", ""))
    if not dato or dato.uid != usuario["id"]: return _json_error("Token no válido", 404)
    dispositivo = await _dispositivo(d.get("dispositivo"))
    if not dispositivo:
        return _json_error("Dispositivo no encontrado", 404)
    try:
        pos = _numero(d.get("posicion"))
    except (TypeError, ValueError):
        return _json_error("Posición no válida")
    try:
        if dispositivo.get("tipo") == "chromecast":
            import pychromecast
            identificador = dispositivo["id"]
            cast = await asyncio.to_thread(pychromecast.get_chromecast_from_host,
                                           (dispositivo["ip"], 8009, None, None, None))
            await asyncio.to_thread(cast.wait, 10)
            tele._chromecasts[identificador] = (cast, asyncio.get_running_loop().time())
            mc = cast.media_controller
            subtitulo = next((x for x in dato.sesion.tokens.values()
                              if x.huella == dato.huella and x.mime == "text/vtt"), None)
            await asyncio.to_thread(mc.play_media,
                                    f"http://{config.LAN_IP}:8095/flujo/{dato.valor}/{dato.nombre}",
                                    dato.mime, d.get("titulo", dato.nombre), current_time=pos,
                                    subtitles=(f"http://{config.LAN_IP}:8095/flujo/{subtitulo.valor}/"
                                               f"{subtitulo.nombre}" if subtitulo else None),
                                    subtitles_lang="es-ES")
            await asyncio.to_thread(mc.block_until_active, 10)
        else:
            control = dispositivo.get("control")
            if not control: return _json_error("La tele DLNA no ofrece AVTransport", 400)
            uri = f"http://{config.LAN_IP}:8095/flujo/{dato.valor}/{dato.nombre}"
            meta = (f"<DIDL-Lite><item><res protocolInfo=\"http-get:*:{html.escape(dato.mime)}:*\">"
                    f"{html.escape(uri)}</res></item></DIDL-Lite>")
            argumentos = (f"<InstanceID>0</InstanceID><CurrentURI>{html.escape(uri)}</CurrentURI>"
                          f"<CurrentURIMetaData>{html.escape(meta)}</CurrentURIMetaData>")
            await tele.dlna(control, "SetAVTransportURI", argumentos)
            await tele.dlna(control, "Play", "<InstanceID>0</InstanceID><Speed>1</Speed>")
    except ImportError: return _json_error("La compatibilidad con Chromecast no está instalada.", 501)
    except Exception as e: return _json_error(str(e), 502)
    tele.registrar(usuario["id"], usuario["rol"], "enviar")
    return {"ok": True}


@router.post("/api/tele/control")
async def control(request: Request):
    d = await _json(request)
    if d is None:
        return _json_error("JSON no válido")
    accion = d.get("accion")
    if accion not in ("play", "pausa", "stop", "buscar"): return _json_error("Acción no válida")
    disp = await _dispositivo(d.get("dispositivo"))
    if not disp:
        return _json_error("Dispositivo no encontrado", 404)
    if disp.get("tipo") == "chromecast":
        conexion = tele._chromecasts.get(disp["id"])
        if not conexion:
            return _json_error("Chromecast no conectado", 409)
        cast, _ = conexion
        metodo = {"play": "play", "pausa": "pause", "stop": "stop", "buscar": "seek"}[accion]
        try:
            segundos = _numero(d.get("segundos"))
            funcion = getattr(cast.media_controller, metodo)
            if accion == "buscar":
                await asyncio.to_thread(funcion, segundos)
            else:
                await asyncio.to_thread(funcion)
            if accion == "stop":
                await asyncio.to_thread(cast.disconnect)
                tele._chromecasts.pop(disp["id"], None)
            else:
                tele._chromecasts[disp["id"]] = (cast, asyncio.get_running_loop().time())
        except (TypeError, ValueError):
            return _json_error("Segundos no válidos")
        return {"ok": True}
    acciones = {"play": "Play", "pausa": "Pause", "stop": "Stop", "buscar": "Seek"}
    try:
        segundos = int(_numero(d.get("segundos")))
    except (TypeError, ValueError):
        return _json_error("Segundos no válidos")
    reloj = f"{segundos // 3600:02d}:{segundos % 3600 // 60:02d}:{segundos % 60:02d}"
    args = f"<InstanceID>0</InstanceID><Unit>REL_TIME</Unit><Target>{reloj}</Target>" if accion == "buscar" else "<InstanceID>0</InstanceID>"
    try: await tele.dlna(disp.get("control"), acciones[accion], args)
    except Exception as e: return _json_error(str(e), 502)
    tele.registrar(request.state.usuario["id"], request.state.usuario["rol"], accion)
    return {"ok": True}


@router.get("/api/tele/estado")
async def estado(dispositivo: str, request: Request):
    disp = await _dispositivo(dispositivo)
    if not disp:
        return _json_error("Dispositivo no encontrado", 404)
    if disp.get("tipo") == "chromecast":
        conexion = tele._chromecasts.get(disp["id"])
        if not conexion:
            return {"estado": "desconocido", "posicion": 0, "duracion": 0}
        cast, _ = conexion
        try:
            estado_cast = await asyncio.to_thread(lambda: cast.media_controller.status)
            return {"estado": estado_cast.player_state or "desconocido",
                    "posicion": estado_cast.current_time or 0,
                    "duracion": estado_cast.duration or 0}
        except Exception:
            return {"estado": "desconocido", "posicion": 0, "duracion": 0}
    try:
        xml = await tele.dlna(disp.get("control"), "GetPositionInfo", "<InstanceID>0</InstanceID>")
        return {"estado": "reproduciendo", "posicion": _segundos(xml, "RelTime"), "duracion": _segundos(xml, "TrackDuration")}
    except Exception: return {"estado": "desconocido", "posicion": 0, "duracion": 0}


def _segundos(xml, etiqueta):
    m = re.search(rf"<{etiqueta}>(\d+):(\d+):(\d+)</{etiqueta}>", xml)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) if m else 0
