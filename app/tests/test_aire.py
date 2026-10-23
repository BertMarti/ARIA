import pytest

from aria import aire


def test_niveles_aire_y_polen():
    assert aire.nivel_aqi(20) == "bueno"
    assert aire.nivel_aqi(21) == "razonable"
    assert aire.nivel_aqi(101) == "extremo"
    assert aire.nivel_polen(10) == "bajo"
    assert aire.nivel_polen(50) == "medio"
    assert aire.nivel_polen(100) == "alto"
    assert aire.nivel_polen(101) == "muy alto"


@pytest.mark.asyncio
async def test_cache_y_fallo(monkeypatch):
    class Respuesta:
        def raise_for_status(self):
            pass

        def json(self):
            return {"hourly": {"time": ["2026-10-24T12:00"], "european_aqi": [12],
                                "grass_pollen": [60], "olive_pollen": [0]}}

    class Cliente:
        llamadas = 0

        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def get(self, *_args, **_kwargs):
            Cliente.llamadas += 1
            return Respuesta()

    aire._CACHE.clear()
    monkeypatch.setattr(aire.httpx, "AsyncClient", Cliente)
    async def coordenadas(*_):
        return {"lat": 40.0, "lon": -3.0, "nombre": "Casa"}
    monkeypatch.setattr(aire.briefing, "_coordenadas", coordenadas)
    aire._CACHE.clear()
    primero = await aire.resumen()
    segundo = await aire.resumen()
    assert primero == segundo
    assert Cliente.llamadas == 1
    assert primero["polen"] == [{"tipo": "gramíneas", "max_hoy": 60.0, "nivel": "alto"}]

    class Fallo(Cliente):
        async def get(self, *_args, **_kwargs):
            raise aire.httpx.ReadError("fallo")

    aire._CACHE.clear()
    monkeypatch.setattr(aire.httpx, "AsyncClient", Fallo)
    assert await aire.resumen() is None
