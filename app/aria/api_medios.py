import asyncio

from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

from . import medios

router = APIRouter()


async def _json(request):
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _error(exc):
    return JSONResponse({"error": str(exc)}, status_code=400)


@router.get("/api/medios/progreso")
async def progreso(request: Request, h: list[str] = Query(default=[])):
    try:
        return {"progreso": await asyncio.to_thread(medios.listar, request.state.usuario["id"], h)}
    except medios.MedioError as exc:
        return _error(exc)


@router.post("/api/medios/progreso")
async def guardar(request: Request):
    data = await _json(request)
    try:
        fila = await asyncio.to_thread(medios.guardar, request.state.usuario["id"], data.get("huella"),
                                       data.get("nombre"), data.get("posicion"), data.get("duracion"))
        return {"progreso": fila}
    except medios.MedioError as exc:
        return _error(exc)
