"""API de Módulos: `GET /api/modulos` (Ajustes → Módulos y los mosaicos de Inicio).

Abierta a los dos roles en `permisos.py`, pero la lista se filtra en el servidor: un `usuario` solo recibe los
módulos activos que su manifiesto le abre, sin herramientas, rutas, variables ni errores. De las variables de
entorno solo sale el nombre y si está definida, nunca el valor."""
from fastapi import APIRouter, Request

from . import modulos

router = APIRouter()


@router.get("/api/modulos")
async def api_modulos(request: Request):
    return {"modulos": await modulos.listar(request.state.usuario["rol"])}
