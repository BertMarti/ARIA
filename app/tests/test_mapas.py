"""Pruebas sin red de los servicios cartográficos públicos."""
import asyncio

import httpx
import pytest

from aria import mapas, tools

_REAL = httpx.AsyncClient


def falso_mapa(monkeypatch, atender):
    llamadas = []

    def handler(req):
        llamadas.append(req)
        return atender(req)

    monkeypatch.setattr(mapas.httpx, "AsyncClient",
                        lambda **kw: _REAL(transport=httpx.MockTransport(handler), **kw))
    return llamadas


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    mapas._cache.clear()
    monkeypatch.setattr(mapas, "_ultimo_nominatim", 0.0)
    yield
    mapas._cache.clear()


def test_busqueda_prioriza_espana_y_cachea(monkeypatch):
    llamadas = falso_mapa(monkeypatch, lambda req: httpx.Response(200, json=[{"display_name": "Lugar", "lat": "40", "lon": "-3"}]))
    assert asyncio.run(mapas.buscar("lugar"))[0]["nombre"] == "Lugar"
    assert asyncio.run(mapas.buscar("lugar"))[0]["lat"] == 40
    assert len(llamadas) == 1 and llamadas[0].url.params["countrycodes"] == "es"


def test_ruta_y_osrm(monkeypatch):
    def respuesta(req):
        assert "/route/v1/foot/-3.0,40.0;-4.0,41.0" in str(req.url)
        return httpx.Response(200, json={"routes": [{"distance": 1500, "duration": 600, "geometry": {"type": "LineString", "coordinates": []}}]})

    falso_mapa(monkeypatch, respuesta)
    r = asyncio.run(mapas.api_ruta("40,-3", "41,-4", "foot"))
    assert r["distancia"] == 1500 and r["duracion"] == 600


def test_tipado_y_coordenadas():
    assert mapas._coord("40, -3") == (40.0, -3.0)
    assert mapas._coord("100, -3") is None
    with pytest.raises(mapas.MapasError):
        mapas._texto("x" * 201)
    assert "mapa_ir" in tools.permitidas("usuario")
    assert "ruta" in tools.relevantes("¿Cómo llego a la farmacia y cuánto se tarda?")


def test_error_externo_en_espanol(monkeypatch):
    falso_mapa(monkeypatch, lambda req: httpx.Response(503))
    r = asyncio.run(mapas.api_buscar("farmacia"))
    assert r.status_code == 400 and "mapas" in r.body.decode().lower()
