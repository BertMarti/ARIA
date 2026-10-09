"""Escaparate público «Conoce a ARIA»: visible sin sesión, sin datos reales y sin abrir el resto de ARIA."""
import re

from fastapi.testclient import TestClient

from aria import config, main

LAN = "https://192.168.1.50"
ESC = config.STATIC_DIR / "escaparate"


def anonimo():
    return TestClient(main.app, base_url=LAN, follow_redirects=False)


def test_portada_sin_sesion_lleva_al_escaparate():
    c = anonimo()
    r = c.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/hola"
    assert c.get("/chat").headers["location"] == "/login"
    r = c.get("/hola")
    assert r.status_code == 200 and "Quiero escuchar a ARIA" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]


def test_sus_archivos_son_publicos_pero_el_resto_no():
    c = anonimo()
    for ruta in ["/static/escaparate/escaparate.css", "/static/escaparate/escaparate.js", "/static/escaparate/ping.js",
                 "/static/escaparate/fuentes/archivo-latin-800-normal.woff2"]:
        assert c.get(ruta).status_code == 200, ruta
    assert c.get("/static/app.js").status_code == 303                        # la app sigue cerrada
    assert c.get("/static/escaparate/../app.js").status_code in (303, 404)   # sin escaparse por «..»
    assert c.get("/api/info").status_code == 401


def test_sin_estilos_ni_scripts_en_linea_y_versionado():
    html = anonimo().get("/hola").text
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "nada de scripts en línea (CSP)"
    assert " style=" not in html and "<style" not in html, "nada de estilos en línea (CSP)"
    assert "/static/escaparate/escaparate.js?v=" in html


def test_sin_llamadas_a_la_api_ni_datos_reales():
    texto = "".join(p.read_text(encoding="utf-8") for p in ESC.glob("*.*") if p.suffix in (".html", ".js", ".css"))
    assert "/api/" not in texto and "fetch(" not in texto
    for prohibido in ():
        assert prohibido not in texto, prohibido
