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


# Huellas (SHA-256, 16 primeros caracteres) de términos privados que nunca deben salir en el escaparate.
# Se guardan cifradas a propósito: el repositorio es público y no debe contener los términos en claro.
HUELLAS_PRIVADAS = {"cdb9e920c729ca5c", "5218e6cf2cde8fba", "4bdbc215d8dc3c57", "1c3cc04ef6615b24", "6a62362c11e91c9f"}


def _huella(t: str) -> str:
    import hashlib
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def test_sin_llamadas_a_la_api_ni_datos_reales():
    texto = "".join(p.read_text(encoding="utf-8") for p in ESC.glob("*.*") if p.suffix in (".html", ".js", ".css"))
    assert "/api/" not in texto and "fetch(" not in texto
    assert not re.search(r"192\.168\.(?!1\.)\d+\.", texto), "solo IPs de ejemplo 192.168.1.x"
    palabras = set(re.findall(r"[\w.-]+", texto.lower()))
    assert not {_huella(w) for w in palabras} & HUELLAS_PRIVADAS, "hay un dato privado en el escaparate"
