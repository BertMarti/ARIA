import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import listas

router = APIRouter()


def _uid(r):
    return r.state.usuario["id"]


def _admin(r):
    return r.state.usuario.get("rol") == "admin"


async def _json(r):
    try:
        d = await r.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _err(e):
    return JSONResponse({"error": str(e)}, status_code=400)


@router.get("/api/listas")
async def listar(request: Request):
    try:
        return {"listas": await asyncio.to_thread(listas.listar, _uid(request))}
    except listas.ListaError as e:
        return JSONResponse({"error": str(e)}, status_code=403)


@router.post("/api/listas")
async def crear(request: Request):
    d = await _json(request)
    try:
        r = await asyncio.to_thread(listas.crear, _uid(request), d.get("nombre"), d.get("icono", "📋"), d.get("compartida_con", "solo_yo"))
        return {"lista": r}
    except listas.ListaError as e:
        return _err(e)


@router.patch("/api/listas/{lista_id:int}")
async def renombrar(lista_id: int, request: Request):
    d = await _json(request)
    try:
        r = await asyncio.to_thread(listas.renombrar, _uid(request), lista_id, d.get("nombre"), d.get("icono"), _admin(request))
    except listas.ListaError as e:
        return _err(e)
    return {"lista": r} if r else JSONResponse({"error": "Lista no encontrada."}, status_code=404)


@router.delete("/api/listas/{lista_id:int}")
async def borrar(lista_id: int, request: Request):
    if not await asyncio.to_thread(listas.borrar, _uid(request), lista_id, _admin(request)):
        return JSONResponse({"error": "Lista no encontrada."}, status_code=404)
    return {"ok": True}


@router.post("/api/listas/{lista_id:int}/items")
async def anadir(lista_id: int, request: Request):
    d = await _json(request)
    try:
        r = await asyncio.to_thread(listas.anadir_items, _uid(request), lista_id, d.get("texto"), d.get("cantidad", ""), _admin(request))
        if not r:
            return JSONResponse({"error": "Lista no encontrada."}, status_code=404)
        return {"items": r}
    except listas.ListaError as e:
        return _err(e)


@router.patch("/api/lista-items/{item_id:int}")
async def marcar(item_id: int, request: Request):
    d = await _json(request)
    r = await asyncio.to_thread(listas.marcar, _uid(request), item_id, bool(d.get("hecho")), _admin(request))
    return {"item": r} if r else JSONResponse({"error": "Artículo no encontrado."}, status_code=404)


@router.delete("/api/lista-items/{item_id:int}")
async def borrar_item(item_id: int, request: Request):
    if not await asyncio.to_thread(listas.borrar_item, _uid(request), item_id, _admin(request)):
        return JSONResponse({"error": "Artículo no encontrado."}, status_code=404)
    return {"ok": True}


@router.post("/api/listas/{lista_id:int}/vaciar")
async def vaciar(lista_id: int, request: Request):
    n = await asyncio.to_thread(listas.vaciar_hechos, _uid(request), lista_id, _admin(request))
    return {"borrados": n}
