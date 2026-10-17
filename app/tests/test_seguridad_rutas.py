"""Barreras de seguridad que recorren TODAS las rutas registradas de la app.

Así, una ruta nueva que se olvide de exigir sesión o de comprobar el origen (CSRF) rompe las pruebas aunque nadie la
haya añadido a una lista a mano.
"""
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from aria import auth, main, usuarios

LAN = "https://192.168.1.50"

# Rutas que responden sin sesión A PROPÓSITO (cada una se protege de otra forma o es pública por diseño).
PUBLICAS = [
    r"/health",                       # comprobación de salud de Docker/Caddy
    r"/internal/tls-ask",             # solo Caddy (por HTTPS da 404: Caddyfile)
    r"/login", r"/login/codigo",      # inicio de sesión
    r"/hola", r"/acceso", r"/acceso/.*",  # escaparate público y solicitud de acceso (con sus propios límites)
    r"/static/.*", r"/sw\.js",        # archivos estáticos
    r"/\.well-known/assetlinks\.json",  # verificación de la app de Android (solo huellas públicas)
    r"/flujo/.*",                     # vídeo para la tele: exige un token de 192 bits en la ruta
    r"/cal/.*",                       # calendario suscrito: exige un token largo en la ruta
    r"/api/app/resumen",              # solo con el token de dispositivo (Bearer); sin él, 401
    r"/",                             # sin sesión redirige al escaparate o al login
]
# Respuestas que NO dan acceso: redirección al login, no autorizado, prohibido, no existe, método no permitido.
SIN_ACCESO = {301, 302, 303, 307, 308, 401, 403, 404, 405}


def _rutas():
    for r in main.app.routes:
        if isinstance(r, APIRoute):
            for metodo in sorted(r.methods - {"HEAD", "OPTIONS"}):
                yield metodo, r.path


def _concreta(ruta: str) -> str:
    """Rellena los parámetros de la ruta con valores plausibles ({cid} → abc, {uid:int} → 1, {x:path} → a/b)."""
    ruta = re.sub(r"\{[^}]*:int\}", "1", ruta)
    ruta = re.sub(r"\{[^}]*:path\}", "a/b", ruta)
    return re.sub(r"\{[^}]+\}", "1", ruta)


def _publica(ruta: str) -> bool:
    return any(re.fullmatch(p, ruta) for p in PUBLICAS)


def test_ninguna_ruta_privada_responde_sin_sesion():
    anonimo = TestClient(main.app, base_url=LAN, follow_redirects=False)
    abiertas = []
    for metodo, plantilla in _rutas():
        ruta = _concreta(plantilla)
        if _publica(plantilla) or _publica(ruta):
            continue
        r = anonimo.request(metodo, ruta, json={}, headers={"Origin": LAN})
        if r.status_code not in SIN_ACCESO:
            abiertas.append(f"{metodo} {plantilla} → {r.status_code}")
    assert not abiertas, "Rutas privadas que responden sin sesión:\n" + "\n".join(abiertas)


def test_ninguna_ruta_que_cambia_cosas_acepta_otro_origen():
    """CSRF: con sesión de administrador, una petición desde otra web (Origin ajeno) se rechaza siempre."""
    admin = usuarios.por_identificador("admin")
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(admin))
    aceptadas = []
    for metodo, plantilla in _rutas():
        if metodo == "GET":
            continue
        ruta = _concreta(plantilla)
        r = c.request(metodo, ruta, json={}, headers={"Origin": "https://web-atacante.example"})
        if r.status_code != 403:
            aceptadas.append(f"{metodo} {plantilla} → {r.status_code}")
    assert not aceptadas, "Rutas que aceptan peticiones de otra web:\n" + "\n".join(aceptadas)


@pytest.mark.parametrize("cabeceras", [
    {"Sec-Fetch-Site": "cross-site"},
    {"Origin": "null"},
])
def test_formularios_de_otra_web_se_rechazan(cabeceras):
    admin = usuarios.por_identificador("admin")
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(admin))
    r = c.post("/api/notas", json={"texto": "csrf"}, headers=cabeceras)
    assert r.status_code == 403


def test_cookie_de_sesion_manipulada_no_vale():
    admin = usuarios.por_identificador("admin")
    buena = auth.crear_sesion(admin)
    for mala in (buena[:-2] + ("AA" if not buena.endswith("AA") else "BB"), "x" * 40, buena + "."):
        c = TestClient(main.app, base_url=LAN, follow_redirects=False)
        c.cookies.set(auth.COOKIE, mala)
        assert c.get("/api/notas").status_code in SIN_ACCESO


def test_xml_con_entidades_se_rechaza_en_el_feed_meteorologico():
    """Defensa en profundidad: un XML con DTD/entidades (p. ej. «mil millones de risas») no se procesa."""
    from aria import avisos_meteo
    malicioso = ('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;">]>'
                 '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>&b;</title></entry></feed>')
    with pytest.raises(ValueError):
        avisos_meteo.parsear(malicioso, zona="Madrid")


def test_heimdall_se_verifica_con_su_autoridad_si_esta(tmp_path, monkeypatch):
    from aria import config, vpn
    ca = tmp_path / "heimdall-ca.crt"
    monkeypatch.setattr(config, "VPN_CA", str(ca))
    assert vpn._verificacion() is False          # sin certificado: comportamiento anterior (y aviso en el registro)
    ca.write_text("certificado de prueba")
    usados = []
    monkeypatch.setattr(vpn.ssl, "create_default_context", lambda cafile: usados.append(cafile) or "contexto")
    monkeypatch.setattr(vpn, "_contexto", None)
    assert vpn._verificacion() == "contexto"     # con certificado: se exige (contexto SSL con esa autoridad)
    assert vpn._verificacion() == "contexto" and usados == [str(ca)]   # se crea una vez y se reutiliza
