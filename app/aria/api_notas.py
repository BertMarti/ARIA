import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import notas

router = APIRouter()

def _u(r): return r.state.usuario["id"]
async def _json(r):
    try: d = await r.json()
    except ValueError: return {}
    return d if isinstance(d, dict) else {}
def _err(e): return JSONResponse({"error": str(e)}, status_code=400)

@router.get("/api/notas")
async def listar(request: Request, estado: str | None = None, categoria: str | None = None):
    try: return {"notas": await asyncio.to_thread(notas.listar, _u(request), estado, categoria)}
    except notas.NotaError as e: return _err(e)

@router.post("/api/notas")
async def crear(request: Request):
    d = await _json(request)
    try: return {"nota": await asyncio.to_thread(notas.crear, _u(request), d.get("texto"), d.get("categoria", "general"), "web")}
    except notas.NotaError as e: return _err(e)

@router.patch("/api/notas/{nid:int}")
async def editar(nid: int, request: Request):
    d = await _json(request)
    try: r = await asyncio.to_thread(notas.editar, _u(request), nid, d.get("texto"), d.get("categoria"), d.get("estado"))
    except notas.NotaError as e: return _err(e)
    return {"nota": r} if r else JSONResponse({"error": "Nota no encontrada."}, status_code=404)

@router.delete("/api/notas/{nid:int}")
async def borrar(nid: int, request: Request):
    if not await asyncio.to_thread(notas.borrar, _u(request), nid):
        return JSONResponse({"error": "Nota no encontrada."}, status_code=404)
    return {"ok": True}
