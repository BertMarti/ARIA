"""Avisos meteorológicos públicos de Meteoalarm para España."""
import time
import xml.etree.ElementTree as ET

from defusedxml import ElementTree as DET
from datetime import datetime, timedelta

import httpx

from . import config, tiempo, ubicacion

URL = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-spain"
_cache = {}
NIVELES = {"minor": 0, "moderate": 1, "severe": 2, "extreme": 3}
EVENTOS = {"rain": "lluvia", "wind": "viento", "thunderstorm": "tormentas", "snow-ice": "nieve/hielo",
           "high-temperature": "calor", "low-temperature": "frío", "fog": "niebla", "coastalevent": "fenómenos costeros",
           "forest-fire": "incendios", "avalanches": "aludes"}


def _texto(root, nombre):
    return next((x.text or "" for x in root.iter() if x.tag.rsplit("}", 1)[-1] == nombre), "").strip()


def parsear(xml: str, zona: str | None = None, provincia: str | None = None) -> list[dict]:
    zona = config.ZONA_METEO if zona is None else zona
    if not zona and not provincia:
        return []
    root = DET.fromstring(xml)   # defusedxml: sin entidades ni DTD (feed externo)
    out = []
    for entry in [x for x in root.iter() if x.tag.rsplit("}", 1)[-1] == "entry"]:
        area, nivel = _texto(entry, "areaDesc"), _texto(entry, "severity").lower()
        identificador = _texto(entry, "identifier")
        import re
        m = re.search(r"\.ES\.\d{12}\.(\d{6})", identificador)
        prov = identificador and (m.group(1)[2:4] if m else None)
        if nivel == "minor" or (provincia and prov != str(provincia).zfill(2)):
            continue
        if zona and zona.casefold() not in area.casefold():
            continue
        onset, expires = _texto(entry, "onset"), _texto(entry, "expires")
        evento = _texto(entry, "event")
        for ingles, espanol in EVENTOS.items():
            if ingles in evento.casefold():
                evento = espanol
                break
        out.append({"clave": _texto(entry, "id") or _texto(entry, "event") + ":" + onset,
                    "area": area, "zona": area, "provincia": prov, "nivel": nivel,
                    "color": {"moderate": "amarillo", "severe": "naranja", "extreme": "rojo"}.get(nivel), "evento": evento,
                    "onset": onset, "expires": expires})
    return out


async def avisos(refrescar=False, provincia=None, zona=None) -> list[dict]:
    global _cache
    provincia = provincia if provincia is not None else await ubicacion.provincia_casa()
    zona = config.ZONA_METEO if zona is None else zona
    if not provincia and not zona:
        return []
    clave = (str(provincia or ""), str(zona or ""))
    guardado = _cache.get(clave, (0.0, []))
    if not refrescar and time.monotonic() - guardado[0] < 1800:
        return guardado[1]
    try:
        async with httpx.AsyncClient(timeout=15) as cl:
            r = await cl.get(URL); r.raise_for_status()
        datos = parsear(r.text, zona, provincia)
        _cache[clave] = (time.monotonic(), datos)
        return datos
    except (httpx.HTTPError, ET.ParseError, ValueError):
        return guardado[1]


async def problemas() -> list:
    from .avisos import Problema
    return [Problema(a["clave"], f"Aviso meteorológico {a['nivel']}: {a['evento']} ({a['area']}).")
            for a in await avisos() if a["nivel"] in ("severe", "extreme")]


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
