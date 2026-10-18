"""Cliente interno del servicio de grabaciones Tapo."""
import os

import httpx


def url_base() -> str:
    return os.environ.get("ARIA_GRABACIONES_URL", "http://grabaciones:8090").rstrip("/")


async def consultar(ruta: str, parametros: dict):
    async with httpx.AsyncClient(base_url=url_base(), timeout=30) as cliente:
        return await cliente.get(ruta, params=parametros)


def cliente_stream(ruta: str, parametros: dict, rango: str | None):
    cabeceras = {"Range": rango} if rango else {}
    return httpx.AsyncClient(base_url=url_base(), timeout=httpx.Timeout(130, connect=5)).stream(
        "GET", ruta, params=parametros, headers=cabeceras)
