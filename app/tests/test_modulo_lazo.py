"""Módulo «Lazo»: mosaico de Inicio y chequeo «caido» por la red interna. Sin red: Lazo falso con MockTransport."""
import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aria import avisos, modulos

REPO_MODULOS = Path(__file__).resolve().parents[2] / "modulos"
pytestmark = pytest.mark.skipif(not (REPO_MODULOS / "lazo").is_dir(), reason="sin la carpeta modulos/ del repositorio")
PUBLICA = "https://lazo.example.com"


class LazoFalso:
    def __init__(self):
        self.sano, self.peticiones = True, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.peticiones.append(request)
        if not self.sano:
            raise httpx.ConnectError("caído", request=request)
        return httpx.Response(200, json={"code": 200, "message": "API is healthy."})


@pytest.fixture
def lazo(monkeypatch):
    falso = LazoFalso()
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(falso), **kw))
    return falso


@pytest.fixture
def cargar(monkeypatch):
    antes = dict(modulos._CARGADOS)
    cargados = []

    def hacer(url=PUBLICA, interna=None):
        for clave, valor in (("LAZO_URL", url), ("LAZO_INTERNA", interna)):
            if valor is None:
                monkeypatch.delenv(clave, raising=False)
            else:
                monkeypatch.setenv(clave, valor)
        hacer.app = FastAPI()
        res = modulos.cargar(hacer.app, REPO_MODULOS, {"lazo"})
        cargados.append(res)
        return res["lazo"]
    yield hacer
    for res in cargados:
        for m in res.values():
            m.retirar()
    modulos._CARGADOS.clear()
    modulos._CARGADOS.update(antes)


def test_se_carga_con_su_mosaico_y_chequeo(cargar):
    m = cargar()
    assert m.estado == "activo" and m.chequeos == ["caido"] and m.herramientas == []


@pytest.mark.parametrize("url", ["http://lazo.example.com", "https://usuario:clave@lazo.example.com",
                                 "https://lazo.example.com/otra", "lazo.example.com"])
def test_url_no_valida_deja_el_modulo_en_error(cargar, url):
    assert cargar(url=url).estado == "error"


def test_sin_url_queda_sin_configurar(cargar):
    assert cargar(url=None).estado != "activo"


def test_mosaico_lleva_a_la_direccion_publica(cargar):
    cargar()
    r = TestClient(cargar.app, base_url="https://aria.example.com").get("/api/modulos/lazo/abrir", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == PUBLICA + "/"
    assert r.headers["cache-control"] == "no-store"


def test_chequeo_por_la_red_interna_con_el_host_publico(cargar, lazo):
    cargar()
    c = avisos.chequeos()["modulo:lazo:caido"]
    assert c.intervalo_s == 300 and c.solo_admin
    assert asyncio.run(c.fn()) == []
    p = lazo.peticiones[-1]
    assert str(p.url) == "http://lazo-caddy/api/health" and p.headers["host"] == "lazo.example.com"
    lazo.sano = False
    [problema] = asyncio.run(c.fn())
    assert problema.clave == "lazo"
