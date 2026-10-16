"""Avisos meteorológicos públicos de Meteoalarm para España."""
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import httpx

from . import config, tiempo

URL = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-spain"
_cache = (0.0, [])
NIVELES = {"minor": 0, "moderate": 1, "severe": 2, "extreme": 3}


def _texto(root, nombre):
    return next((x.text or "" for x in root.iter() if x.tag.rsplit("}", 1)[-1] == nombre), "").strip()


def parsear(xml: str, zona: str | None = None) -> list[dict]:
    zona = config.ZONA_METEO if zona is None else zona
    if not zona:
        return []
    root = ET.fromstring(xml)
    out = []
    for entry in [x for x in root.iter() if x.tag.rsplit("}", 1)[-1] == "entry"]:
        area, nivel = _texto(entry, "areaDesc"), _texto(entry, "severity").lower()
        if zona.casefold() not in area.casefold() or NIVELES.get(nivel, 0) < 1:
            continue
        onset, expires = _texto(entry, "onset"), _texto(entry, "expires")
        out.append({"clave": _texto(entry, "id") or _texto(entry, "event") + ":" + onset,
                    "area": area, "nivel": nivel, "evento": _texto(entry, "event"),
                    "onset": onset, "expires": expires})
    return out


async def avisos(refrescar=False) -> list[dict]:
    global _cache
    if not config.ZONA_METEO:
        return []
    if not refrescar and time.monotonic() - _cache[0] < 1800:
        return _cache[1]
    try:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.get(URL); r.raise_for_status()
        datos = parsear(r.text)
        _cache = (time.monotonic(), datos)
        return datos
    except (httpx.HTTPError, ET.ParseError):
        return _cache[1]


async def problemas() -> list:
    from .avisos import Problema
    return [Problema(a["clave"], f"Aviso meteorológico {a['nivel']}: {a['evento']} ({a['area']}).") for a in await avisos()]


def _fecha(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


async def propuestas(ahora=None) -> list[dict]:
    """Genera recordatorios preventivos para lluvia o viento naranja/rojo de hoy."""
    ahora = ahora or tiempo.ahora()
    out = []
    for a in await avisos():
        if a["nivel"] not in ("severe", "extreme") or not any(x in a["evento"].lower() for x in ("lluv", "viento")):
            continue
        inicio = _fecha(a["onset"])
        if not inicio or inicio.astimezone(ahora.tzinfo).date() != ahora.date():
            continue
        inicio = inicio.astimezone(ahora.tzinfo)
        cuando = inicio.replace(second=0, microsecond=0) - timedelta(hours=1)
        if cuando <= ahora:
            continue
        out.append({"clave": f"meteo:{a['clave']}", "tipo": "meteo", "titulo": "¿Te aviso para proteger la casa?",
                    "detalle": f"Hay aviso de {a['evento'].lower()} para {a['area']}. Te recuerdo recoger la ropa o cerrar ventanas.",
                    "herramienta": "recordatorio", "args": {"texto": "Recoger la ropa / cerrar ventanas", "cuando": cuando.strftime("%Y-%m-%dT%H:%M")},
                    "caduca": cuando.timestamp()})
    return out
