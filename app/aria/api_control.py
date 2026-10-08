"""API del control parental (/api/red/control/...). Todo es SOLO de administrador (no está en la lista
blanca de `usuario` de permisos.py). Cada operación lleva la clave de UN dispositivo del inventario; no hay
ninguna acción «para todos». Ver control.py."""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import control, red

router = APIRouter()


def _err(msg: str, estado: int = 400) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=estado)


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


async def _aplicar() -> dict:
    """Aplica ya en SHIELD-DNS. Si falla, el estado queda guardado y el planificador lo reintenta."""
    r = await control.reconciliar()
    return {"aplicado": bool(r.get("ok")), "aviso": r.get("error")}


@router.get("/api/red/control")
async def estado():
    return await asyncio.to_thread(control.resumen_api)


@router.post("/api/red/control/pausa")
async def pausar(request: Request):
    d = await _json(request)
    minutos = d.get("minutos")
    if not isinstance(d.get("clave"), str) or (minutos is not None and (isinstance(minutos, bool) or not isinstance(minutos, int))):
        return _err("Datos no válidos.")
    try:
        r = await asyncio.to_thread(control.pausar, d["clave"], minutos)
    except control.ControlError as e:
        return _err(str(e))
    return {**r, **await _aplicar()}


@router.post("/api/red/control/reanudar")
async def reanudar(request: Request):
    d = await _json(request)
    if not isinstance(d.get("clave"), str):
        return _err("Datos no válidos.")
    hubo = await asyncio.to_thread(control.reanudar, d["clave"])
    return {"estaba_pausado": hubo, **await _aplicar()}


@router.post("/api/red/control/servicio")
async def servicio(request: Request):
    d = await _json(request)
    if not isinstance(d.get("clave"), str) or not isinstance(d.get("servicio"), str) or not isinstance(d.get("bloquear"), bool):
        return _err("Datos no válidos.")
    try:
        if d["bloquear"]:
            sid = await asyncio.to_thread(control.bloquear_servicio, d["clave"], d["servicio"])
        else:
            sid = await asyncio.to_thread(control.desbloquear_servicio, d["clave"], d["servicio"])
    except control.ControlError as e:
        return _err(str(e))
    return {"servicio": sid, **await _aplicar()}


@router.post("/api/red/control/horarios")
async def crear_horario(request: Request):
    d = await _json(request)
    servicio_ = d.get("servicio")
    if not isinstance(d.get("clave"), str) or (servicio_ is not None and not isinstance(servicio_, str)) \
            or not isinstance(d.get("desde"), str) or not isinstance(d.get("hasta"), str):
        return _err("Datos no válidos.")
    try:
        r = await asyncio.to_thread(control.crear_horario, d["clave"], servicio_ or None, d.get("dias"), d["desde"], d["hasta"])
    except control.ControlError as e:
        return _err(str(e))
    return {**r, **await _aplicar()}


@router.delete("/api/red/control/horarios/{hid}")
async def borrar_horario(hid: int):
    if not await asyncio.to_thread(control.borrar_horario, hid):
        return _err("Horario no encontrado.", 404)
    return {"ok": True, **await _aplicar()}


@router.post("/api/red/control/aplicar")
async def aplicar():
    return await _aplicar()
