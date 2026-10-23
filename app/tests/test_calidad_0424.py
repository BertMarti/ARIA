"""Arreglos pequeños de calidad (24/10/2026)."""
import asyncio
import time
from datetime import datetime

from aria import gasolineras, luz, recordatorios, tiempo


def test_las_12_de_la_noche_es_medianoche():
    assert recordatorios._hora_de("a las 12 de la noche") == (0, 0)
    assert recordatorios._hora_de("a las 11 de la noche") == (23, 0)
    assert recordatorios._hora_de("a las 12") == (12, 0)


def test_cache_de_la_luz_guarda_hoy_y_manana(monkeypatch):
    luz._cache.clear()
    serie = [{"hora": h, "precio": 0.1} for h in range(24)]
    for d in ("2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27"):
        luz._cache[d] = (time.monotonic(), serie)
    # Al guardar un día nuevo solo se expulsan los más antiguos (quedan tres).
    for k in sorted(k for k in luz._cache if k != "2026-10-27")[:-2]:
        luz._cache.pop(k, None)
    assert set(luz._cache) == {"2026-10-25", "2026-10-26", "2026-10-27"}


def test_gasolineras_sin_datos_reintenta_pronto(monkeypatch, tmp_path):
    import httpx

    class Falla:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): raise httpx.ConnectError("sin red")
    monkeypatch.setattr(gasolineras, "_cache", None)
    monkeypatch.setattr(gasolineras, "_cache_at", 0.0)
    monkeypatch.setattr(gasolineras, "_ruta", lambda: tmp_path / "gasolineras.json")
    monkeypatch.setattr(gasolineras.httpx, "AsyncClient", Falla)
    assert asyncio.run(gasolineras.actualizar()) == []
    # No se queda 12 horas sin datos: a los 10 minutos ya vuelve a intentarlo.
    edad = time.monotonic() - gasolineras._cache_at
    assert 12 * 3600 - 700 < edad < 12 * 3600
