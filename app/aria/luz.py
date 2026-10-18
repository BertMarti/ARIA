"""Precio de la luz (PVPC, tarifa regulada de España) por horas, de la API pública de Red Eléctrica (REE).

Sin clave. Se pide una vez por día y se guarda en memoria. Los precios salen en €/kWh.
"""
import time
from datetime import date

import httpx

from . import config, tiempo

URL = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"
_cache: dict = {}


class LuzError(Exception):
    """El precio de la luz no está disponible ahora."""


def activo() -> bool:
    return config.LUZ


async def precios(dia: date | None = None) -> list[dict]:
    """[{hora: 0..23, precio: €/kWh}] del día (por defecto, hoy)."""
    dia = dia or tiempo.hoy()
    clave = dia.isoformat()
    c = _cache.get(clave)
    if c and time.monotonic() - c[0] < 6 * 3600:
        return c[1]
    try:
        async with httpx.AsyncClient(timeout=8, headers={"Accept": "application/json"}) as cl:
            r = await cl.get(URL, params={"start_date": f"{clave}T00:00", "end_date": f"{clave}T23:59", "time_trunc": "hour"})
            r.raise_for_status()
            incluidos = r.json().get("included") or []
    except (httpx.HTTPError, ValueError) as e:
        raise LuzError("El precio de la luz no está disponible ahora.") from e
    serie = next((x for x in incluidos if str(x.get("type", "")).upper() == "PVPC"), None)
    if not serie:
        raise LuzError("Red Eléctrica aún no ha publicado el precio de ese día.")
    out = []
    for v in serie.get("attributes", {}).get("values", []):
        try:
            out.append({"hora": int(str(v["datetime"])[11:13]), "precio": round(float(v["value"]) / 1000, 4)})
        except (KeyError, TypeError, ValueError):
            continue
    if len(out) < 20:
        raise LuzError("Los datos del precio de la luz están incompletos.")
    for k in [k for k in _cache if k != clave]:
        _cache.pop(k, None)
    _cache[clave] = (time.monotonic(), out)
    return out


def resumen(serie: list[dict], hora_actual: int | None = None) -> dict:
    """Media, hora más barata y más cara, precio actual y las tres horas más baratas que quedan."""
    hora_actual = tiempo.ahora().hour if hora_actual is None else hora_actual
    media = sum(x["precio"] for x in serie) / len(serie)
    barata, cara = min(serie, key=lambda x: x["precio"]), max(serie, key=lambda x: x["precio"])
    ahora = next((x for x in serie if x["hora"] == hora_actual), None)
    quedan = sorted((x for x in serie if x["hora"] >= hora_actual), key=lambda x: x["precio"])[:3]
    nivel = None
    if ahora:
        nivel = "barata" if ahora["precio"] <= media * .9 else "cara" if ahora["precio"] >= media * 1.1 else "media"
    return {"media": round(media, 4), "barata": barata, "cara": cara, "ahora": ahora, "nivel": nivel,
            "mejores_restantes": sorted(quedan, key=lambda x: x["hora"]), "serie": serie}


async def hoy() -> dict:
    return resumen(await precios())


def texto(r: dict) -> str:
    def eur(p): return f"{p:.3f}".replace(".", ",") + " €/kWh"
    partes = [f"Precio medio de la luz hoy: {eur(r['media'])}.",
              f"Lo más barato, a las {r['barata']['hora']}:00 ({eur(r['barata']['precio'])}); "
              f"lo más caro, a las {r['cara']['hora']}:00 ({eur(r['cara']['precio'])})."]
    if r.get("ahora"):
        partes.append(f"Ahora mismo: {eur(r['ahora']['precio'])} ({r['nivel']}).")
    if r.get("mejores_restantes"):
        partes.append("Mejores horas que quedan: " + ", ".join(f"{x['hora']}:00" for x in r["mejores_restantes"]) + ".")
    return " ".join(partes)


def franja(serie: list[dict], horas: int = 3, cara: bool = False) -> dict | None:
    """Las `horas` seguidas más baratas (o más caras) del día: {desde, hasta, media}. «hasta» es la hora en que acaba."""
    por_hora = {x["hora"]: x["precio"] for x in serie}
    mejor = None
    for inicio in range(0, 25 - horas):
        tramo = [por_hora.get(h) for h in range(inicio, inicio + horas)]
        if None in tramo:
            continue
        media = sum(tramo) / horas
        if mejor is None or (media > mejor["media"] if cara else media < mejor["media"]):
            mejor = {"desde": inicio, "hasta": inicio + horas, "media": round(media, 4)}
    return mejor


def texto_manana(serie: list[dict]) -> str:
    """Aviso de la tarde: cuándo conviene poner lavadora, lavavajillas o cargar el coche mañana."""
    def eur(p): return f"{p:.3f}".replace(".", ",") + " €/kWh"
    barata, cara = franja(serie), franja(serie, cara=True)
    media = sum(x["precio"] for x in serie) / len(serie)
    partes = [f"Luz de mañana: lo más barato, de {barata['desde']}:00 a {barata['hasta']}:00 ({eur(barata['media'])} de media)."]
    if cara:
        partes.append(f"Evita de {cara['desde']}:00 a {cara['hasta']}:00 ({eur(cara['media'])}).")
    partes.append(f"Media del día: {eur(media)}. Buen momento para la lavadora o el lavavajillas: las horas baratas.")
    return " ".join(partes)
