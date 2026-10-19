"""API de los dispositivos del hogar. Las credenciales nunca salen de este módulo."""
import asyncio
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from . import (config, hogar_cache as cache, hogar_camaras as camaras_video, hogar_eventos as eventos,
               hogar_govee as govee, hogar_grabaciones as grabaciones, hogar_router as router_hogar,
               hogar_tapo as tapo, hogar_vigilancia as vigilancia)

router = APIRouter()
_acciones = []


def _error(texto, estado=400): return JSONResponse({"error": texto}, status_code=estado)


async def _integracion(modulo, funcion, nombre, clave=None, fresco=60):
    if not modulo.configurado(): return {"configurado": False, "datos": []}
    try:
        datos = await (cache.obtener(clave, funcion, fresco) if clave else funcion())
        return {"configurado": True, "datos": datos}
    except Exception: return {"configurado": True, "error": f"No se pudo consultar {nombre}.", "datos": []}


# Cada sección por separado: la pantalla pinta cada una en cuanto llega (antes esperaba a la más lenta).
@router.get("/api/hogar/luces")
async def hogar_luces():
    return await _integracion(govee, govee.luces, "Govee", "luces", 30)


@router.get("/api/hogar/camaras")
async def hogar_camaras_estado():
    return await _integracion(tapo, tapo.camaras, "las cámaras", "camaras", 120)


@router.get("/api/hogar/router")
async def hogar_router_estado():
    return await _integracion(router_hogar, router_hogar.estado, "el router", "router", 90)


@router.get("/api/hogar")
async def hogar(request: Request):
    u = request.state.usuario
    es_admin = u["rol"] == "admin"
    ver = es_admin or bool(u.get("ver_camaras"))
    nada = asyncio.sleep(0, result=None)
    luces, router_d, camaras = await asyncio.gather(
        _integracion(govee, govee.luces, "Govee", "luces", 30) if es_admin else nada,
        _integracion(router_hogar, router_hogar.estado, "el router", "router", 90) if es_admin else asyncio.sleep(0, result=None),
        _integracion(tapo, tapo.camaras, "las cámaras", "camaras", 120) if ver else asyncio.sleep(0, result=None))
    resultado = {}
    if es_admin: resultado.update(luces=luces, router=router_d)
    if ver: resultado["camaras"] = camaras
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
    try:
        r = await govee.cambiar(identificador, encendida, brillo, int(color[1:], 16) if color else None)
        cache.invalidar("luces")
        return r
    except govee.GoveeError as e: return _error(str(e), 502)


@router.post("/api/hogar/camaras/privacidad")
async def privacidad(request: Request):
    if not _limite(): return _error("Demasiadas acciones; espera un minuto.", 429)
    try: d = await request.json()
    except ValueError: return _error("Datos no válidos.")
    if not isinstance(d, dict) or not isinstance(d.get("ip"), str) or not isinstance(d.get("activa"), bool):
        return _error("Datos no válidos.")
    try:
        fila = await tapo.privacidad(d["ip"], d["activa"])   # solo cámaras ya vistas o configuradas
        cache.invalidar("camaras")
        return {"camara": fila}
    except tapo.TapoError as e: return _error(str(e), 400 if "no encontrada" in str(e) else 502)
    except Exception: return _error("No se pudo cambiar la privacidad.", 502)


@router.post("/api/hogar/router/invitados")
async def invitados(request: Request):
    if not _limite(): return _error("Demasiadas acciones; espera un minuto.", 429)
    try: d = await request.json()
    except ValueError: return _error("Datos no válidos.")
    if not isinstance(d, dict) or not isinstance(d.get("activa"), bool): return _error("Datos no válidos.")
    try:
        r = await router_hogar.invitados(d["activa"])
        cache.invalidar("router")
        return r
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
async def ver_vigilancia(candidatos: int = 0):
    """Estado de la vigilancia. Con `candidatos=1` añade los dispositivos de la red para elegir (lento: consulta
    también las concesiones DHCP del router); sin él usa la última lista conocida."""
    if not router_hogar.configurado():
        return {"disponible": False}
    try:
        lista = await _candidatos() if candidatos else await cache.obtener("router-conectados", router_hogar.conectados, 90)
    except Exception:  # noqa: BLE001
        lista = []
    return {"disponible": True, **await asyncio.to_thread(vigilancia.resumen, lista)}


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
    if request.state.usuario["rol"] != "admin" and d["campo"] != "led":   # quien solo mira: solo la luz de la cámara
        return _error("No tienes permiso para esto.", 403)
    try:
        fila = await tapo.ajustar(d["ip"], d["campo"], d["valor"])
        cache.invalidar("camaras")
        return {"camara": fila}
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


# Eventos (detecciones con la casa vacía): solo administradores, como el resto del hogar (no están en la lista blanca).
@router.get("/api/hogar/eventos")
async def listar_eventos(limite: int = 50):
    return {"eventos": await asyncio.to_thread(eventos.listar, limite)}


@router.get("/api/hogar/eventos/{evento_id}/foto")
async def foto_evento(evento_id: int):
    datos = await asyncio.to_thread(eventos.foto, evento_id)
    if not datos: return _error("Ese evento no tiene foto.", 404)
    return Response(datos, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/api/hogar/eventos/vistos")
async def eventos_vistos():
    return {"vistos": await asyncio.to_thread(eventos.marcar_vistos)}


async def precalentar() -> None:
    """Mantiene la pantalla Hogar lista: el router (~6-9 s) y las luces cada 2 min; las cámaras cada 10 min (las de
    batería no se despiertan más de la cuenta). La primera visita ya no espera."""
    await asyncio.sleep(20)
    vuelta = 0
    while True:
        try:
            if router_hogar.configurado():
                await cache.refrescar("router", router_hogar.estado)
                await cache.refrescar("router-conectados", router_hogar.conectados)   # misma sesión (caché interna)
            if govee.configurado():
                await cache.refrescar("luces", govee.luces)
            if tapo.configurado() and vuelta % 5 == 0:
                await cache.refrescar("camaras", tapo.camaras)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - nunca para: la pantalla seguirá funcionando bajo demanda
            pass
        vuelta += 1
        await asyncio.sleep(120)
