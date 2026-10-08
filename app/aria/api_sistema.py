"""API del sistema en directo y del reinicio de la Raspberry."""
import asyncio
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import avisos, telemetria

router = APIRouter()


@router.get("/api/sistema/listas")
async def listas():
    from . import shield
    try:
        return await shield.listas()
    except shield.ShieldError as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@router.post("/api/sistema/listas/actualizar")
async def actualizar_listas():
    from . import shield
    try:
        return await shield.actualizar_listas()
    except shield.ShieldError as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@router.get("/api/sistema/directo")
async def directo():
    try:
        return await asyncio.to_thread(telemetria.directo)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=503)


@router.get("/api/sistema/historial")
async def historial(horas: int = 1):
    try:
        return {"historial": await asyncio.to_thread(telemetria.historial, horas)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post("/api/sistema/reiniciar")
async def reiniciar(request: Request):
    try:
        d = await request.json()
    except ValueError:
        d = {}
    if not isinstance(d, dict) or d.get("confirmar") is not True:
        return JSONResponse({"error": "Debes confirmar el reinicio."}, status_code=400)
    try:
        resultado = await asyncio.to_thread(telemetria.solicitar_reinicio)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=429)
    u = request.state.usuario
    await avisos.emitir("sistema", "aviso", f"🔄 Reiniciando la Raspberry a petición de {u['nombre']}…", "control")
    return resultado
