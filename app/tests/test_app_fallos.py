"""Informes de cierres de la aplicación Android."""
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from aria import api_app, auth, avisos, db, main, usuarios


BASE = "https://192.168.1.50"


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


@pytest.fixture(autouse=True)
def limitador_limpio(monkeypatch):
    monkeypatch.setattr(api_app, "_lim_fallos", api_app.avisos.Limitador(5, 3600))


def cliente(usuario):
    c = TestClient(main.app, base_url=BASE, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(usuario))
    return c


def informe(**cambios):
    datos = {"version": "3.2.5", "android": 15, "modelo": "Pixel de prueba",
             "excepcion": "java.lang.NullPointerException", "traza": "at io.example.MainActivity.onCreate(MainActivity.java:1)",
             "cuando": 1792233600000}
    datos.update(cambios)
    return datos


def avisos_de_app():
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute("SELECT * FROM avisos WHERE tipo='app'")]


def test_guarda_y_avisa(ana):
    r = cliente(ana).post("/api/app/fallos", json=informe())
    assert r.status_code == 200
    with closing(db._con()) as con:
        fallo = dict(con.execute("SELECT * FROM app_fallos").fetchone())
    assert fallo["user_id"] == ana["id"] and fallo["excepcion"] == informe()["excepcion"]
    assert len(avisos_de_app()) == 1 and "Android 15" in avisos_de_app()[0]["texto"]


def test_deduplica_misma_excepcion_y_version(admin):
    c = cliente(admin)
    assert c.post("/api/app/fallos", json=informe()).status_code == 200
    assert c.post("/api/app/fallos", json=informe()).status_code == 200
    assert len(avisos_de_app()) == 1


def test_recorta_campos_largos(admin):
    r = cliente(admin).post("/api/app/fallos", json=informe(
        version="v" * 200, modelo="m" * 200, excepcion="e" * 500, traza="t" * 5000))
    assert r.status_code == 200
    with closing(db._con()) as con:
        fallo = dict(con.execute("SELECT * FROM app_fallos").fetchone())
    assert len(fallo["version"]) == 100 and len(fallo["modelo"]) == 120
    assert len(fallo["excepcion"]) == 300 and len(fallo["traza"]) == 4000


def test_rechaza_cuerpo_demasiado_grande(admin):
    assert cliente(admin).post("/api/app/fallos", json=informe(traza="x" * 8100)).status_code == 413


def test_usuario_no_puede_leer_fallos(ana):
    assert cliente(ana).get("/api/app/fallos").status_code == 403


def test_limite_por_usuario_y_hora(admin, monkeypatch):
    monkeypatch.setattr(api_app, "_lim_fallos", avisos.Limitador(5, 3600))
    c = cliente(admin)
    for n in range(5):
        assert c.post("/api/app/fallos", json=informe(version=f"3.2.{n}")).status_code == 200
    assert c.post("/api/app/fallos", json=informe(version="3.2.99")).status_code == 429


def test_post_sin_origin_con_cookie_funciona(ana):
    assert cliente(ana).post("/api/app/fallos", json=informe()).status_code == 200


def test_post_con_origin_ajeno_se_rechaza(ana):
    r = cliente(ana).post("/api/app/fallos", json=informe(), headers={"Origin": "https://otra.example.com"})
    assert r.status_code == 403
