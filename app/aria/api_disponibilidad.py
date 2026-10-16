"""API admin del histórico de disponibilidad."""
import asyncio
from fastapi import APIRouter, Request

from . import disponibilidad

router = APIRouter()


def _dias(valor: int) -> int:
    return valor if valor in (1, 7, 30) else 1


@router.get("/api/disponibilidad")
async def api_disponibilidad(dias: int = 1):
    return await asyncio.to_thread(disponibilidad.resumen, _dias(dias))


@router.get("/api/disponibilidad/incidentes")
async def api_incidentes(dias: int = 30):
    return {"incidentes": await asyncio.to_thread(disponibilidad.incidentes, _dias(dias))}
