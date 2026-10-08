"""API de Automatizaciones, solo para administradores."""
import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from . import automatizaciones

router = APIRouter()
def _u(r): return r.state.usuario
async def _json(r):
    try: d = await r.json()
    except ValueError: return {}
    return d if isinstance(d, dict) else {}
def _err(e, status=400): return JSONResponse({"error": str(e)}, status_code=status)

@router.get("/api/automatizaciones")
async def listar(request: Request): return {"automatizaciones": await asyncio.to_thread(automatizaciones.listar, _u(request)["id"]), "acciones": sorted(automatizaciones.ACCIONES), "tipos": list(automatizaciones.avisos.TIPOS)}
@router.get("/api/automatizaciones/registro")
async def registro(request: Request): return {"registro": await asyncio.to_thread(automatizaciones.registro, _u(request)["id"])}
@router.post("/api/automatizaciones")
async def crear(request: Request):
    try: return {"automatizacion": await asyncio.to_thread(automatizaciones.crear, _u(request)["id"], await _json(request))}
    except automatizaciones.AutomatizacionError as e: return _err(e)
@router.patch("/api/automatizaciones/{aid}")
async def editar(aid: int, request: Request):
    try: r = await asyncio.to_thread(automatizaciones.actualizar, _u(request)["id"], aid, await _json(request))
    except automatizaciones.AutomatizacionError as e: return _err(e)
    return {"automatizacion": r} if r else _err("Automatización no encontrada.", 404)
@router.delete("/api/automatizaciones/{aid}")
async def borrar(aid: int, request: Request): return {"ok": True} if await asyncio.to_thread(automatizaciones.borrar, _u(request)["id"], aid) else _err("Automatización no encontrada.", 404)
@router.post("/api/automatizaciones/{aid}/probar")
async def probar(aid: int, request: Request):
    r = await asyncio.to_thread(automatizaciones.obtener, _u(request)["id"], aid)
    if not r: return _err("Automatización no encontrada.", 404)
    return {"resultado": await automatizaciones.disparar(_u(request)["id"], r, {"simulado": True}, True)}
