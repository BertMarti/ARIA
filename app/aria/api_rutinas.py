"""API de Rutinas (Ajustes → Rutinas). Todo es del usuario de la sesión: una rutina ajena da 404 igual que una
que no existe. permisos.py la abre a los dos roles; el agente se valida contra el rol en `rutinas`."""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import agentes, avisos, cerebros, rutinas

router = APIRouter()

_lim_cambios = avisos.Limitador(60, 3600)
_lim_ejecutar = avisos.Limitador(6, 3600)


def _u(request: Request) -> dict:
    return request.state.usuario


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _error(e: Exception, codigo: int = 400) -> JSONResponse:
    return JSONResponse({"error": str(e)}, status_code=codigo)


def _no_existe() -> JSONResponse:
    return JSONResponse({"error": "Rutina no encontrada."}, status_code=404)


def _demasiadas() -> JSONResponse:
    return JSONResponse({"error": "Demasiadas peticiones seguidas; espera un poco."}, status_code=429)


@router.get("/api/rutinas")
async def api_rutinas(request: Request):
    u = _u(request)
    return {"rutinas": await asyncio.to_thread(rutinas.listar, u["id"]),
            "agentes": agentes.disponibles(u["rol"]), "canales": list(rutinas.CANALES),
            "limites": {"max": rutinas.MAX_POR_USUARIO, "min_horas": rutinas.MIN_HORAS,
                        "max_prompt": rutinas.MAX_PROMPT, "max_nombre": rutinas.MAX_NOMBRE},
            "nube": cerebros.hay_nube()}


@router.post("/api/rutinas")
async def api_rutina_crear(request: Request):
    u = _u(request)
    if not _lim_cambios.permitir(u["id"]):
        return _demasiadas()
    try:
        r = await asyncio.to_thread(rutinas.crear, u["id"], u["rol"], await _json(request))
    except rutinas.RutinaError as e:
        return _error(e)
    return {"rutina": r}


@router.patch("/api/rutinas/{rid}")
async def api_rutina_editar(rid: int, request: Request):
    u = _u(request)
    if not _lim_cambios.permitir(u["id"]):
        return _demasiadas()
    try:
        r = await asyncio.to_thread(rutinas.actualizar, u["id"], u["rol"], rid, await _json(request))
    except rutinas.RutinaError as e:
        return _error(e)
    return {"rutina": r} if r else _no_existe()


@router.delete("/api/rutinas/{rid}")
async def api_rutina_borrar(rid: int, request: Request):
    if not await asyncio.to_thread(rutinas.borrar, _u(request)["id"], rid):
        return _no_existe()
    return {"ok": True}


@router.post("/api/rutinas/{rid}/ejecutar")
async def api_rutina_ejecutar(rid: int, request: Request):
    """«Ejecutar ahora»: se lanza en segundo plano y el resultado llega por sus canales y a la campana."""
    u = _u(request)
    r = await asyncio.to_thread(rutinas.obtener, u["id"], rid)
    if not r:
        return _no_existe()
    if r["en_curso"]:
        return JSONResponse({"error": "Esa rutina ya se está ejecutando."}, status_code=409)
    if not _lim_ejecutar.permitir(u["id"]):
        return _demasiadas()
    rutinas.en_segundo_plano(rutinas.ejecutar(r))
    return {"ok": True, "nube": cerebros.hay_nube()}
