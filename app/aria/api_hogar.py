"""API de los dispositivos del hogar. Las credenciales nunca salen de este módulo."""
import asyncio
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from . import (config, hogar_camaras as camaras_video, hogar_govee as govee, hogar_grabaciones as grabaciones,
               hogar_router as router_hogar, hogar_tapo as tapo, hogar_vigilancia as vigilancia)

router = APIRouter()
_acciones = []


def _error(texto, estado=400): return JSONResponse({"error": texto}, status_code=estado)


async def _integracion(modulo, funcion, nombre):
    if not modulo.configurado(): return {"configurado": False, "datos": []}
    try: return {"configurado": True, "datos": await funcion()}
    except Exception: return {"configurado": True, "error": f"No se pudo consultar {nombre}.", "datos": []}


@router.get("/api/hogar")
async def hogar(request: Request):
    es_admin = request.state.usuario["rol"] == "admin"
    luces, router_d, camaras = await asyncio.gather(
        _integracion(govee, govee.luces, "Govee"),
        _integracion(router_hogar, router_hogar.estado, "el router") if es_admin else asyncio.sleep(0, result=None),
        _integracion(tapo, tapo.camaras, "las cámaras") if es_admin else asyncio.sleep(0, result=None))
    resultado = {"luces": luces}
    if es_admin: resultado.update(router=router_d, camaras=camaras)
    return resultado


def _limite():
    ahora = time.monotonic(); _acciones[:] = [x for x in _acciones if ahora - x < 60]
    if len(_acciones) >= 30: return False
    _acciones.append(ahora); return True


@router.post("/api/hogar/luces/{identificador}")
async def cambiar_luz(identificador: str, request: Request):
    if not _limite(): return _error("Demasiadas acciones; espera un minuto.", 429)
    try: d = await request.json()
    except ValueError: return _error("Datos no válidos.")
    if not isinstance(d, dict): return _error("Datos no válidos.")
    encendida = d.get("encendida")
    brillo = d.get("brillo")
    color = d.get("color")
    if encendida is not None and not isinstance(encendida, bool): return _error("La alimentación no es válida.")
    if brillo is not None and (isinstance(brillo, bool) or not isinstance(brillo, int) or not 1 <= brillo <= 100): return _error("El brillo debe estar entre 1 y 100.")
    if color is not None and (not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color)): return _error("El color debe tener formato #rrggbb.")
    try: return await govee.cambiar(identificador, encendida, brillo, int(color[1:], 16) if color else None)
    except govee.GoveeError as e: return _error(str(e), 502)


@router.post("/api/hogar/camaras/privacidad")
async def privacidad(request: Request):
    if not _limite(): return _error("Demasiadas acciones; espera un minuto.", 429)
    try: d = await request.json()
    except ValueError: return _error("Datos no válidos.")
    if not isinstance(d, dict) or not isinstance(d.get("ip"), str) or not isinstance(d.get("activa"), bool):
        return _error("Datos no válidos.")
    try: return {"camara": await tapo.privacidad(d["ip"], d["activa"])}   # solo cámaras ya vistas o configuradas
    except tapo.TapoError as e: return _error(str(e), 400 if "no encontrada" in str(e) else 502)
    except Exception: return _error("No se pudo cambiar la privacidad.", 502)


@router.post("/api/hogar/router/invitados")
async def invitados(request: Request):
    if not _limite(): return _error("Demasiadas acciones; espera un minuto.", 429)
    try: d = await request.json()
    except ValueError: return _error("Datos no válidos.")
    if not isinstance(d, dict) or not isinstance(d.get("activa"), bool): return _error("Datos no válidos.")
    try: return await router_hogar.invitados(d["activa"])
    except router_hogar.RouterError as e: return _error(str(e), 502)


@router.post("/api/hogar/router/reiniciar")
async def reiniciar():
    if not _limite(): return _error("Demasiadas acciones; espera un minuto.", 429)
    try: return await router_hogar.reiniciar()
    except router_hogar.RouterError as e: return _error(str(e), 502)


async def _candidatos() -> list:
    try:
        return await router_hogar.conocidos()
    except Exception:  # noqa: BLE001 - sin router se muestra lo guardado
        return []


@router.get("/api/hogar/vigilancia")
async def ver_vigilancia():
    if not router_hogar.configurado():
        return {"disponible": False}
    return {"disponible": True, **await asyncio.to_thread(vigilancia.resumen, await _candidatos())}


@router.post("/api/hogar/vigilancia")
async def cambiar_vigilancia(request: Request):
    if not _limite(): return _error("Demasiadas acciones; espera un minuto.", 429)
    try: d = await request.json()
    except ValueError: return _error("Datos no válidos.")
    if not isinstance(d, dict): return _error("Datos no válidos.")
    candidatos = await _candidatos()
    try:
        await asyncio.to_thread(vigilancia.configurar, d, candidatos)
    except ValueError as e:
        return _error(str(e))
    return {"disponible": True, **await asyncio.to_thread(vigilancia.resumen, candidatos)}


@router.get("/api/hogar/camaras/foto")
async def foto_camara(ip: str = "", miniatura: int = 0):
    """Imagen de una cámara (solo administradores: no está en la lista blanca de `usuario`). Con `miniatura=1` vale una
    de los últimos 10 minutos (para la cuadrícula, sin despertar a las de batería cada vez)."""
    if not camaras_video.disponible() or not camaras_video.flujo(ip):
        return _error("Cámara no encontrada.", 404)
    try:
        datos = await camaras_video.foto(ip, camaras_video.EDAD_MINIATURA if miniatura else 0)
    except Exception:  # noqa: BLE001
        return _error("La cámara no ha enviado imagen (puede estar dormida o en modo privacidad).", 502)
    return Response(datos, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/api/hogar/camaras/ajuste")
async def ajuste_camara(request: Request):
    if not _limite(): return _error("Demasiadas acciones; espera un minuto.", 429)
    try: d = await request.json()
    except ValueError: return _error("Datos no válidos.")
    if not isinstance(d, dict) or not isinstance(d.get("ip"), str) or not isinstance(d.get("valor"), bool) \
            or d.get("campo") not in tapo.AJUSTES:
        return _error("Datos no válidos.")
    try: return {"camara": await tapo.ajustar(d["ip"], d["campo"], d["valor"])}
    except tapo.TapoError as e: return _error(str(e), 400 if "no encontrada" in str(e) or "no tiene" in str(e) else 502)


@router.post("/api/hogar/camaras/mover")
async def mover_camara(request: Request):
    try: d = await request.json()
    except ValueError: return _error("Datos no válidos.")
    if not isinstance(d, dict) or not isinstance(d.get("ip"), str) or d.get("direccion") not in tapo.MOVIMIENTOS:
        return _error("Datos no válidos.")
    try:
        await tapo.mover(d["ip"], d["direccion"])
        return {"ok": True}
    except tapo.TapoError as e: return _error(str(e), 400 if "no encontrada" in str(e) or "no se puede" in str(e) else 502)


def _camara_grabacion(ip):
    nombre = camaras_video.flujo(ip)
    return nombre if nombre and ip in config.TAPO_CAMARAS else None


@router.get("/api/hogar/camaras/grabaciones/dias")
async def dias_grabaciones(ip: str = ""):
    nombre = _camara_grabacion(ip)
    if not nombre: return _error("Cámara no encontrada.", 404)
    try:
        r = await grabaciones.consultar("/dias", {"cam": nombre})
        return Response(r.content, status_code=r.status_code, media_type="application/json")
    except Exception: return _error("No se pudo consultar la cámara.", 502)


@router.get("/api/hogar/camaras/grabaciones")
async def fragmentos_grabaciones(ip: str = "", dia: str = ""):
    nombre = _camara_grabacion(ip)
    if not nombre or not dia: return _error("Cámara o día no válido.", 400)
    try:
        r = await grabaciones.consultar("/fragmentos", {"cam": nombre, "dia": dia})
        return Response(r.content, status_code=r.status_code, media_type="application/json")
    except Exception: return _error("No se pudo consultar la cámara.", 502)


@router.get("/api/hogar/camaras/grabaciones/clip")
async def clip_grabacion(request: Request, ip: str = "", dia: str = "", inicio: int | None = None, fin: int | None = None):
    nombre = _camara_grabacion(ip)
    if not nombre or not dia or inicio is None or fin is None: return _error("Cámara o fragmento no válido.", 400)
    cliente = grabaciones.cliente_stream("/clip", {"cam": nombre, "dia": dia, "inicio": inicio, "fin": fin}, request.headers.get("range"))
    try:
        upstream = await cliente.__aenter__()
        if upstream.status_code >= 400:
            contenido = await upstream.aread()
            await cliente.__aexit__(None, None, None)
            return Response(contenido, status_code=upstream.status_code,
                            media_type=upstream.headers.get("content-type", "application/json"))
        cabeceras = {k: upstream.headers[k] for k in
                     ("content-length", "content-range", "accept-ranges", "cache-control") if k in upstream.headers}

        async def cuerpo():
            try:
                async for bloque in upstream.aiter_bytes():
                    yield bloque
            finally:
                await cliente.__aexit__(None, None, None)

        return StreamingResponse(cuerpo(), status_code=upstream.status_code,
                                 media_type=upstream.headers.get("content-type", "video/mp4"), headers=cabeceras)
    except Exception:
        await cliente.__aexit__(None, None, None)
        return _error("No se pudo preparar el vídeo.", 502)
