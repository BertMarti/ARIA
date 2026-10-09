import asyncio
from datetime import date

import httpx
import pytest

from aria import luz, tools


def correr(c):
    return asyncio.run(c)


def respuesta(precios_mwh):
    valores = [{"value": v, "datetime": f"2026-10-09T{h:02d}:00:00.000+02:00"} for h, v in enumerate(precios_mwh)]
    return {"included": [{"type": "Precio mercado spot", "attributes": {"values": []}},
                         {"type": "PVPC", "attributes": {"title": "PVPC", "values": valores}}]}


@pytest.fixture
def ree(monkeypatch):
    estado = {"peticiones": 0, "datos": respuesta([100 + h * 5 for h in range(24)]), "caido": False}
    def manejar(req):
        estado["peticiones"] += 1
        assert req.url.host == "apidatos.ree.es" and req.url.params["time_trunc"] == "hour"
        return httpx.Response(503) if estado["caido"] else httpx.Response(200, json=estado["datos"])
    real = httpx.AsyncClient
    monkeypatch.setattr(luz.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(manejar), **kw))
    luz._cache.clear()
    return estado


def test_precios_en_euros_por_kwh_y_cache(ree):
    p = correr(luz.precios(date(2026, 10, 9)))
    assert len(p) == 24 and p[0] == {"hora": 0, "precio": 0.1} and p[23]["precio"] == 0.215
    correr(luz.precios(date(2026, 10, 9)))
    assert ree["peticiones"] == 1


def test_resumen_de_horas():
    serie = [{"hora": h, "precio": p} for h, p in enumerate([0.2] * 8 + [0.1, 0.05, 0.3] + [0.2] * 13)]
    r = luz.resumen(serie, hora_actual=9)
    assert r["barata"] == {"hora": 9, "precio": 0.05} and r["cara"]["hora"] == 10
    assert r["nivel"] == "barata" and [x["hora"] for x in r["mejores_restantes"]][0] == 9
    t = luz.texto(r)
    assert "a las 9:00 (0,050 €/kWh)" in t and "Ahora mismo" in t


def test_api_caida_da_error_legible(ree):
    ree["caido"] = True
    with pytest.raises(luz.LuzError):
        correr(luz.precios(date(2026, 10, 9)))
    assert "no está disponible" in correr(tools.precio_luz())


def test_sin_pvpc_publicado(ree):
    ree["datos"] = {"included": []}
    with pytest.raises(luz.LuzError, match="publicado"):
        correr(luz.precios(date(2026, 10, 10)))
