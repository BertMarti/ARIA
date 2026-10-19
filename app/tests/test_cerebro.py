"""Contrato de la topología del Cerebro y aislamiento por rol."""
from fastapi.testclient import TestClient
import pytest

from aria import api_cerebro, auth, main, usuarios

LAN = "https://192.168.1.50"


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("cerebro-ana@example.com", "Ana Cerebro", "usuario", "clave-larga-ana")


def cliente_de(u):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def test_admin_recibe_grafo_coherente(admin):
    r = cliente_de(admin).get("/api/cerebro")
    assert r.status_code == 200
    d = r.json()
    ids = {n["id"] for n in d["nodos"]}
    assert any(n["id"] == "aria" for n in d["nodos"])
    assert all(e["origen"] in ids and e["destino"] in ids for e in d["enlaces"])


def test_nodos_tienen_descripcion_y_mejoras_sin_ips(admin):
    nodos = cliente_de(admin).get("/api/cerebro").json()["nodos"]
    textos = [n["que_hace"] for n in nodos] + [m for n in nodos for m in n["mejoras"]]
    assert all(isinstance(n["que_hace"], str) and n["que_hace"] for n in nodos)
    assert all(isinstance(n["mejoras"], list) and n["mejoras"] for n in nodos)
    assert not any(__import__("re").search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", texto) for texto in textos)


def test_usuario_ve_un_mapa_recortado(ana, monkeypatch):
    vistos = []
    monkeypatch.setattr(api_cerebro.registro, "listar", lambda **kw: vistos.append(kw.get("user_id")) or [])
    r = cliente_de(ana).get("/api/cerebro")
    assert r.status_code == 200
    nodos = r.json()["nodos"]
    ids = {n["id"] for n in nodos}
    assert "aria" in ids and "agente-seguridad" not in ids
    assert not any(i.startswith("servicio-") or i in ("tunel", "copias", "datos-db") for i in ids)
    assert "usuarios activos" not in next(n for n in nodos if n["id"] == "aria")["datos"]
    assert vistos == [ana["id"]]   # solo su actividad


def test_actividad_del_usuario_solo_la_suya(ana, monkeypatch):
    vistos = []
    monkeypatch.setattr(api_cerebro.registro, "listar", lambda **kw: vistos.append(kw.get("user_id")) or [])
    assert cliente_de(ana).get("/api/cerebro/actividad?desde=0").status_code == 200
    assert vistos == [ana["id"]]


def test_fuente_rota_no_rompe_la_respuesta(admin, monkeypatch):
    monkeypatch.setattr(api_cerebro.cerebros, "estado", lambda: (_ for _ in ()).throw(RuntimeError("fallo")))
    r = cliente_de(admin).get("/api/cerebro")
    assert r.status_code == 200
    assert any(n["estado"] == "mal" and n["detalle"] == "sin datos" for n in r.json()["nodos"])


def test_actividad_no_expone_argumentos(admin, monkeypatch):
    monkeypatch.setattr(api_cerebro.registro, "listar", lambda **_: [{"ts": 10, "herramienta": "x", "agente": "aria", "origen": "chat", "ok": 1, "args": "secreto"}])
    d = cliente_de(admin).get("/api/cerebro/actividad?desde=0").json()
    assert d["actividad"] == [{"ts": 10, "herramienta": "x", "agente": "aria", "origen": "chat", "ok": 1}]
