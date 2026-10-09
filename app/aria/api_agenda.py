"""API de agenda y cumpleaños. Todos los ids se comprueban con el usuario de sesión."""
import asyncio
from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from . import agenda

router = APIRouter()

def _u(r): return r.state.usuario["id"]
async def _json(r):
    try: d = await r.json()
    except ValueError: return {}
    return d if isinstance(d, dict) else {}
def _err(e): return JSONResponse({"error": str(e)}, status_code=400)
def _404(text): return JSONResponse({"error": text}, status_code=404)

@router.get("/api/agenda")
async def listar(request: Request, desde: str | None = None, hasta: str | None = None):
    hoy=date.today(); desde=desde or hoy.isoformat(); hasta=hasta or (hoy+timedelta(days=31)).isoformat()
    try: return {"eventos": await asyncio.to_thread(agenda.listar_eventos,_u(request),desde,hasta)}
    except agenda.AgendaError as e: return _err(e)

@router.post("/api/agenda")
async def crear(request: Request):
    try: return {"evento": await asyncio.to_thread(agenda.crear_evento,_u(request),await _json(request))}
    except agenda.AgendaError as e: return _err(e)

@router.patch("/api/agenda/{eid:int}")
async def editar(eid:int,request:Request):
    try: r=await asyncio.to_thread(agenda.editar_evento,_u(request),eid,await _json(request))
    except agenda.AgendaError as e:return _err(e)
    return {"evento":r} if r else _404("Evento no encontrado.")

@router.delete("/api/agenda/{eid:int}")
async def borrar(eid:int,request:Request):
    return {"ok":True} if await asyncio.to_thread(agenda.borrar_evento,_u(request),eid) else _404("Evento no encontrado.")

@router.get("/api/cumpleanos")
async def listar_cumples(request:Request,dias:int=30):
    try:return {"cumpleanos":await asyncio.to_thread(agenda.listar_cumpleanos,_u(request),dias)}
    except (agenda.AgendaError,ValueError) as e:return _err(e)

@router.post("/api/cumpleanos")
async def crear_cumple(request:Request):
    try:return {"cumpleanos":await asyncio.to_thread(agenda.crear_cumple,_u(request),await _json(request))}
    except agenda.AgendaError as e:return _err(e)

@router.patch("/api/cumpleanos/{cid:int}")
async def editar_cumple(cid:int,request:Request):
    try:r=await asyncio.to_thread(agenda.editar_cumple,_u(request),cid,await _json(request))
    except agenda.AgendaError as e:return _err(e)
    return {"cumpleanos":r} if r else _404("Cumpleaños no encontrado.")

@router.delete("/api/cumpleanos/{cid:int}")
async def borrar_cumple(cid:int,request:Request):
    return {"ok":True} if await asyncio.to_thread(agenda.borrar_cumple,_u(request),cid) else _404("Cumpleaños no encontrado.")


# --- Exportar y suscribirse desde otros calendarios ---
@router.get("/api/agenda/ics")
async def descargar_ics(request: Request):
    texto = await asyncio.to_thread(agenda.ics, _u(request))
    return Response(texto, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="agenda-aria.ics"'})


@router.get("/api/agenda/suscripcion")
async def ver_suscripcion(request: Request):
    return {"activa": await asyncio.to_thread(agenda.tiene_suscripcion, _u(request))}


@router.post("/api/agenda/suscripcion")
async def nueva_suscripcion(request: Request):
    """Devuelve el token UNA vez (solo se guarda su huella); el anterior deja de valer."""
    token = await asyncio.to_thread(agenda.crear_suscripcion, _u(request))
    return {"activa": True, "ruta": f"/cal/{token}.ics"}


@router.delete("/api/agenda/suscripcion")
async def quitar_suscripcion(request: Request):
    await asyncio.to_thread(agenda.borrar_suscripcion, _u(request))
    return {"activa": False}


@router.get("/cal/{token}.ics")
async def calendario_publico(token: str):
    """Ruta sin sesión para las apps de calendario: el token largo y aleatorio hace de llave."""
    uid = await asyncio.to_thread(agenda.usuario_de_token, token)
    if uid is None:
        return Response("No encontrado", status_code=404, media_type="text/plain")
    return Response(await asyncio.to_thread(agenda.ics, uid), media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "private, max-age=900"})
