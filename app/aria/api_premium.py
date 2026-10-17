"""API de activación local de ARIA Premium."""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import premium

router = APIRouter()


@router.get("/api/premium")
async def estado():
    return await asyncio.to_thread(premium.estado)


@router.post("/api/premium/licencia")
async def licencia(request: Request):
    try:
        datos = await request.json()
        if not isinstance(datos, dict) or not isinstance(datos.get("licencia"), str):
            raise premium.PremiumError("Falta la licencia.")
        return await asyncio.to_thread(premium.instalar_licencia, datos.get("licencia"))
    except (ValueError, TypeError, premium.PremiumError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.post("/api/premium/prueba")
async def prueba():
    try:
        return await asyncio.to_thread(premium.empezar_prueba)
    except premium.PremiumError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.delete("/api/premium/licencia")
async def borrar():
    return await asyncio.to_thread(premium.quitar_licencia)
