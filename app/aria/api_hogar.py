"""API de los dispositivos del hogar. Las credenciales nunca salen de este módulo."""
import asyncio
import re
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import hogar_govee as govee, hogar_router as router_hogar, hogar_tapo as tapo, hogar_vigilancia as vigilancia

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
        return await router_hogar.conectados()
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
