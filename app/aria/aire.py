"""Calidad del aire y polen de Open-Meteo, sin clave y con caché breve."""
import time
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from . import briefing, config

URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
_CACHE: OrderedDict[tuple[float, float], tuple[float, dict]] = OrderedDict()
_CACHE_S = 3600
_POLEN = {"olive_pollen": "olivo", "grass_pollen": "gramíneas", "birch_pollen": "abedul",
          "alder_pollen": "aliso", "mugwort_pollen": "artemisa", "ragweed_pollen": "ambrosía"}
_AIRE = ((20, "bueno"), (40, "razonable"), (60, "moderado"), (80, "malo"), (100, "muy malo"))


def nivel_aqi(valor):
    if valor is None:
        return None
    return next((texto for limite, texto in _AIRE if valor <= limite), "extremo")


def nivel_polen(valor):
    # Umbrales orientativos en granos/m³: 0–10 bajo, 11–50 medio, 51–100 alto,
    # más de 100 muy alto. No existe una escala clínica universal.
    if valor <= 10:
        return "bajo"
    if valor <= 50:
        return "medio"
    if valor <= 100:
        return "alto"
    return "muy alto"


def _ahora_indice(horas: list[str]) -> int:
    ahora = datetime.now(ZoneInfo(config.TZ)).replace(tzinfo=None)
    return min(range(len(horas)), key=lambda i: abs(datetime.fromisoformat(horas[i]) - ahora))


async def resumen(lugar: dict | None = None) -> dict | None:
    """Devuelve aire y polen actuales y máximos de hoy; None si falla el servicio."""
    try:
        async with httpx.AsyncClient(timeout=4) as cliente:
            ub = await briefing._coordenadas(cliente, lugar)
            if not ub:
                return None
            # La ubicación se redondea al guardarla; usa la misma precisión que el tiempo.
            coord = (round(float(ub["lat"]), 2), round(float(ub["lon"]), 2))
            ahora = time.monotonic()
            guardado = _CACHE.get(coord)
            if guardado and ahora - guardado[0] < _CACHE_S:
                return guardado[1]
            r = await cliente.get(URL, params={
                "latitude": coord[0], "longitude": coord[1],
                "hourly": "european_aqi,olive_pollen,grass_pollen,birch_pollen,alder_pollen,mugwort_pollen,ragweed_pollen",
                "timezone": config.TZ, "forecast_days": 1,
            })
            r.raise_for_status()
            hourly = r.json()["hourly"]
            idx = _ahora_indice(hourly["time"])
            aqi = hourly.get("european_aqi", [])[idx]
            polen = []
            for clave, tipo in _POLEN.items():
                valores = [float(x or 0) for x in hourly.get(clave, [])]
                maximo = round(max(valores), 1) if valores else 0
                if maximo:
                    polen.append({"tipo": tipo, "max_hoy": maximo, "nivel": nivel_polen(maximo)})
            resultado = {"aqi_ahora": aqi, "nivel_aqi": nivel_aqi(aqi), "polen": polen}
            _CACHE[coord] = (ahora, resultado)
            _CACHE.move_to_end(coord)
            while len(_CACHE) > 4:
                _CACHE.popitem(last=False)
            return resultado
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, OSError):
        return None
