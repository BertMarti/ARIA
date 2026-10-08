"""API del centro de información."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import busqueda, informacion

router = APIRouter()


def _uid(request):
    return request.state.usuario["id"]


def _error(e):
    return JSONResponse({"error": str(e)}, status_code=400)


@router.get("/api/informacion/noticias")
async def api_noticias(request: Request, tema: str = "España"):
    try: return {"tema": tema, "noticias": await informacion.noticias(tema)}
    except (informacion.InformacionError, busqueda.BusquedaError) as e: return _error(e)


@router.get("/api/informacion/resumen")
async def api_resumen(request: Request, tema: str = "España"):
    try: return await informacion.resumen(tema)
    except (informacion.InformacionError, busqueda.BusquedaError) as e: return _error(e)


@router.get("/api/informacion/temas")
async def api_temas(request: Request):
    return {"temas": informacion.temas(_uid(request))}


@router.post("/api/informacion/temas")
async def api_temas_guardar(request: Request):
    try: return {"temas": informacion.guardar_temas(_uid(request), (await request.json()).get("temas", []))}
    except (informacion.InformacionError, AttributeError, TypeError, ValueError) as e: return _error(e)


@router.delete("/api/informacion/temas")
async def api_tema_borrar(request: Request, tema: str = ""):
    try:
        actuales = informacion.temas(_uid(request)); actuales.remove(tema)
        return {"temas": informacion.guardar_temas(_uid(request), actuales)}
    except (informacion.InformacionError, ValueError) as e: return _error(e)


@router.get("/api/informacion/mercados")
async def api_mercados(request: Request):
    return await informacion.mercados(_uid(request))


@router.get("/api/informacion/buscar")
async def api_buscar(request: Request, q: str = ""):
    try: return {"resultados": await informacion.buscar_simbolos(q)}
    except informacion.InformacionError as e: return _error(e)


@router.get("/api/informacion/seguimiento")
async def api_seguimiento(request: Request):
    return {"valores": informacion.lista(_uid(request))}


@router.post("/api/informacion/seguimiento")
async def api_seguimiento_anadir(request: Request):
    try:
        d = await request.json()
        return informacion.anadir_valor(_uid(request), d.get("simbolo", ""), d.get("nombre"), d.get("tipo"),
                                        d.get("cantidad"), d.get("precio_medio"))
    except (informacion.InformacionError, AttributeError, TypeError, ValueError) as e: return _error(e)


@router.delete("/api/informacion/seguimiento/{identificador}")
async def api_seguimiento_borrar(identificador: int, request: Request):
    if not informacion.borrar_valor(_uid(request), identificador):
        return JSONResponse({"error": "Valor no encontrado"}, status_code=404)
    return {"ok": True}


@router.get("/api/informacion/historico")
async def api_historico(request: Request, simbolo: str = "", dias: int = 30):
    try: return await informacion.historico(simbolo, max(1, min(dias, 365)))
    except informacion.InformacionError as e: return _error(e)
