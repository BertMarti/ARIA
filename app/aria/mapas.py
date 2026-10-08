"""Servicios cartográficos libres: Nominatim, OSRM y Overpass.

Las llamadas pasan por ARIA para poder identificar el cliente, respetar los límites
de los servicios públicos y no exponer sus respuestas directamente al navegador.
"""
import asyncio
import math
import re
import time
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from . import config

router = APIRouter()
NOMINATIM = "https://nominatim.openstreetmap.org"
OSRM = "https://router.project-osrm.org"
OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "ARIA/2.0 (asistente domestico autoalojado; +https://github.com/BertMarti/ARIA)"
_cache: dict[tuple, tuple[float, object]] = {}
_cache_lock = asyncio.Lock()
_nominatim_lock = asyncio.Lock()
_ultimo_nominatim = 0.0
_ahora = time.monotonic
_COORD = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*,\s*(-?\d+(?:[.,]\d+)?)\s*$")
_TIPOS = {
    "farmacia": ('"amenity"="pharmacy"', "farmacias"),
    "gasolinera": ('"amenity"="fuel"', "gasolineras"),
    "supermercado": ('"shop"="supermarket"', "supermercados"),
    "restaurante": ('"amenity"="restaurant"', "restaurantes"),
    "cajero": ('"amenity"="atm"', "cajeros"),
}
MAX_TEXTO = 200


class MapasError(Exception):
    pass


def _texto(valor, maximo=MAX_TEXTO):
    valor = " ".join(str(valor or "").split())
    if not valor or len(valor) > maximo:
        raise MapasError(f"El texto debe tener entre 1 y {maximo} caracteres.")
    return valor


def _coord(valor):
    m = _COORD.match(str(valor or ""))
    if not m:
        return None
    try:
        lat, lon = (float(x.replace(",", ".")) for x in m.groups())
    except ValueError:
        return None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None
    return lat, lon


async def _get(url, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=4), headers={"User-Agent": USER_AGENT}) as cl:
            r = await cl.get(url, **kwargs)
        if r.status_code != 200:
            raise MapasError("El servicio de mapas no está disponible ahora mismo.")
        return r.json()
    except MapasError:
        raise
    except httpx.TimeoutException:
        raise MapasError("El servicio de mapas ha tardado demasiado; inténtalo de nuevo.")
    except (httpx.HTTPError, ValueError):
        raise MapasError("No puedo conectar con el servicio de mapas ahora mismo.")


async def _nominatim(params):
    global _ultimo_nominatim
    clave = ("nominatim", tuple(sorted(params.items())))
    async with _cache_lock:
        dato = _cache.get(clave)
        if dato and _ahora() - dato[0] < 86400:
            return dato[1]
    async with _nominatim_lock:
        espera = 1.0 - (_ahora() - _ultimo_nominatim)
        if espera > 0:
            await asyncio.sleep(espera)
        resultado = await _get(f"{NOMINATIM}/search", params={**params, "format": "jsonv2", "limit": 10})
        _ultimo_nominatim = _ahora()
    if not isinstance(resultado, list):
        raise MapasError("La búsqueda de lugares ha devuelto una respuesta no válida.")
    async with _cache_lock:
        _cache[clave] = (_ahora(), resultado)
    return resultado


async def buscar(q: str) -> list:
    q = _texto(q)
    resultados = await _nominatim({"q": q, "countrycodes": "es", "addressdetails": 1})
    if not resultados:
        resultados = await _nominatim({"q": q, "addressdetails": 1})
    return [{"nombre": str(x.get("display_name", ""))[:240], "lat": float(x["lat"]), "lon": float(x["lon"])}
            for x in resultados if isinstance(x, dict) and x.get("lat") and x.get("lon")]


async def _resolver(lugar: str):
    if not lugar or str(lugar).strip().lower() == "casa":
        if config.LAT is None or config.LON is None:
            raise MapasError("No hay coordenadas configuradas para «casa».")
        return config.LAT, config.LON, "casa"
    c = _coord(lugar)
    if c:
        return *c, str(lugar).strip()
    r = await buscar(lugar)
    if not r:
        raise MapasError(f"No encuentro el lugar «{lugar}».")
    return r[0]["lat"], r[0]["lon"], r[0]["nombre"]


def _error(e):
    return JSONResponse({"error": str(e)}, status_code=400)


@router.get("/api/mapa/buscar")
async def api_buscar(q: str = Query(..., min_length=1, max_length=MAX_TEXTO)):
    try:
        return {"resultados": await buscar(q)}
    except MapasError as e:
        return _error(e)


@router.get("/api/mapa/ruta")
async def api_ruta(desde: str = Query(..., max_length=MAX_TEXTO), hasta: str = Query(..., max_length=MAX_TEXTO),
                   modo: str = Query("driving")):
    try:
        if modo not in ("driving", "foot", "bike"):
            raise MapasError("El modo debe ser driving, foot o bike.")
        a, b = await asyncio.gather(_resolver(_texto(desde)), _resolver(_texto(hasta)))
        datos = await _get(f"{OSRM}/route/v1/{modo}/{a[1]},{a[0]};{b[1]},{b[0]}",
                           params={"overview": "full", "geometries": "geojson"})
        ruta = (datos.get("routes") or [None])[0]
        if not ruta:
            raise MapasError("No se ha encontrado una ruta entre esos lugares.")
        return {"desde": a[2], "hasta": b[2], "modo": modo, "distancia": ruta.get("distance", 0),
                "duracion": ruta.get("duration", 0), "geometria": ruta.get("geometry", {})}
    except MapasError as e:
        return _error(e)


@router.get("/api/mapa/cerca")
async def api_cerca(lugar: str = Query("casa", max_length=MAX_TEXTO), tipo: str = Query(...)):
    try:
        if tipo not in _TIPOS:
            raise MapasError("Tipo no permitido. Usa farmacia, gasolinera, supermercado, restaurante o cajero.")
        lat, lon, nombre = await _resolver(_texto(lugar) if lugar else "casa")
        filtro, _ = _TIPOS[tipo]
        # Los supermercados usan shop, el resto usa amenity; el filtro procede de la lista cerrada.
        consulta = f"[out:json][timeout:10];nwr[{filtro}](around:5000,{lat},{lon});out center;"
        datos = await _get(OVERPASS, params={"data": consulta})
        sitios = []
        for x in datos.get("elements", []) if isinstance(datos, dict) else []:
            p = x.get("center", x)
            if not p.get("lat") or not p.get("lon"):
                continue
            d = _distancia(lat, lon, float(p["lat"]), float(p["lon"]))
            tags = x.get("tags") or {}
            sitios.append({"nombre": tags.get("name") or "Sin nombre", "lat": p["lat"], "lon": p["lon"], "metros": round(d)})
        return {"lugar": nombre, "tipo": tipo, "resultados": sorted(sitios, key=lambda x: x["metros"])[:5]}
    except MapasError as e:
        return _error(e)


def _distancia(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _formato_distancia(metros):
    return f"{metros / 1000:.1f} km" if metros >= 1000 else f"{metros} m"


def _enlace(lugar=""):
    return "#mapa" + (f"?lugar={quote(str(lugar))}" if lugar else "")
