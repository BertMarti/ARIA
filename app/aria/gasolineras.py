"""Precios oficiales de carburantes en España, sin clave y con copia local."""
import json
import math
import time
from pathlib import Path

import httpx

from . import config

URL = "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/PreciosCarburantes/EstacionesTerrestres/"
_cache: list[dict] | None = None
_cache_at = 0.0


def activo() -> bool:
    return config.GASOLINERAS


def _numero(v):
    try:
        s = str(v or "").strip()
        return float(s.replace(".", "").replace(",", ".") if "," in s else s)
    except (TypeError, ValueError):
        return None


def parsear(payload) -> list[dict]:
    """Extrae únicamente los campos que necesita la consulta."""
    filas = payload.get("ListaEESSPrecio", []) if isinstance(payload, dict) else payload
    out = []
    for f in filas or []:
        lat, lon = _numero(f.get("Latitud")), _numero(f.get("Longitud (WGS84)"))
        g95, diesel = _numero(f.get("Precio Gasolina 95 E5")), _numero(f.get("Precio Gasoleo A"))
        if lat is None or lon is None or (g95 is None and diesel is None):
            continue
        out.append({"lat": lat, "lon": lon, "nombre": str(f.get("Rótulo") or "").strip(),
                    "direccion": " ".join(" ".join(str(f.get(k) or "").split()) for k in ("Dirección", "Municipio")),
                    "gasolina95": g95, "diesel": diesel})
    return out


def _ruta() -> Path:
    return config.DATA_DIR / "gasolineras.json"


def _leer() -> list[dict]:
    try:
        j = json.loads(_ruta().read_text())
        return j.get("estaciones", j) if isinstance(j, (dict, list)) else []
    except (OSError, ValueError):
        return []


async def actualizar() -> list[dict]:
    """Actualiza como máximo cada 12 horas; si falla conserva la copia anterior."""
    global _cache, _cache_at
    if _cache is not None and time.monotonic() - _cache_at < 12 * 3600:
        return _cache
    ruta = _ruta()
    try:
        if ruta.exists() and time.time() - ruta.stat().st_mtime < 12 * 3600:
            _cache = _leer(); _cache_at = time.monotonic(); return _cache
        async with httpx.AsyncClient(timeout=60, headers={"Accept": "application/json"}) as cl:
            r = await cl.get(URL)
            r.raise_for_status()
            datos = parsear(r.json())
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"estaciones": datos}, ensure_ascii=False))
        _cache, _cache_at = datos, time.monotonic()
        return datos
    except (httpx.HTTPError, ValueError, OSError):
        datos = _leer()
        # Sin copia previa no se guarda una lista vacía 12 h: se vuelve a intentar a los 10 minutos.
        _cache, _cache_at = datos, (time.monotonic() if datos else time.monotonic() - 12 * 3600 + 600)
        return datos


def _distancia(a, b, c, d) -> float:
    y = math.radians(c - a)
    x = math.radians(d - b) * math.cos(math.radians((a + c) / 2))
    return 6371 * math.sqrt(x * x + y * y)


async def cerca(lat=None, lon=None, combustible="gasolina95", radio_km=10, n=5) -> list[dict]:
    lat, lon = config.LAT if lat is None else float(lat), config.LON if lon is None else float(lon)
    if lat is None or lon is None:
        return []
    if combustible not in ("gasolina95", "diesel"):
        raise ValueError("Combustible no válido")
    radio_km = min(max(float(radio_km or 10), 1.0), 50.0)   # el radio lo elige el modelo: acotado
    out = []
    for e in await actualizar():
        precio = e.get(combustible)
        distancia = _distancia(lat, lon, e["lat"], e["lon"])
        if precio is not None and distancia <= float(radio_km):
            out.append({**e, "precio": precio, "distancia_km": round(distancia, 2)})
    return sorted(out, key=lambda x: (x["precio"], x["distancia_km"]))[:min(max(1, int(n)), 10)]
