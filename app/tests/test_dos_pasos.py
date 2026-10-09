import base64
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from aria import auth, dos_pasos, main, usuarios

LAN = "https://192.168.1.50"


def test_vector_rfc6238():
    assert dos_pasos.codigo(b"12345678901234567890", 59 // 30) == "287082"
    assert dos_pasos.codigo(b"12345678901234567890", 1111111109 // 30) == "081804"


def secreto_de(uri: str) -> bytes:
    b32 = parse_qs(urlparse(uri).query)["secret"][0]
    return base64.b32decode(b32 + "=" * (-len(b32) % 8))


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def test_activar_verificar_antirrepeticion_y_recuperacion(ana):
    p = dos_pasos.preparar(ana["id"], "ana@example.com")
    assert p["uri"].startswith("otpauth://totp/ARIA%3Aana%40example.com?secret=")
    s, t = secreto_de(p["uri"]), 1_800_000_000
    with pytest.raises(dos_pasos.DosPasosError):
        dos_pasos.activar(ana["id"], "000000", ahora=t)
    rec = dos_pasos.activar(ana["id"], dos_pasos.codigo(s, t // 30), ahora=t)
    assert len(rec) == 8 and dos_pasos.activo(ana["id"])
    siguiente = dos_pasos.codigo(s, t // 30 + 1)
    assert dos_pasos.verificar(ana["id"], siguiente, ahora=t + 30)
    assert not dos_pasos.verificar(ana["id"], siguiente, ahora=t + 31)            # no se puede repetir
    assert not dos_pasos.verificar(ana["id"], dos_pasos.codigo(s, t // 30 + 5), ahora=t + 30)   # demasiado lejos
    assert dos_pasos.verificar(ana["id"], rec[0].upper(), ahora=t + 60)           # recuperación, una vez
    assert not dos_pasos.verificar(ana["id"], rec[0], ahora=t + 60) and dos_pasos.quedan_recuperacion(ana["id"]) == 7


def test_secreto_guardado_cifrado(ana):
    p = dos_pasos.preparar(ana["id"], "ana")
    crudo = secreto_de(p["uri"])
    from contextlib import closing
    from aria import db
    with closing(db._con()) as con:
        guardado = con.execute("SELECT secreto FROM dos_pasos WHERE user_id=?", (ana["id"],)).fetchone()[0]
    assert base64.b64decode(guardado) != crudo


def test_login_con_dos_pasos(ana):
    p = dos_pasos.preparar(ana["id"], "ana")
    s = secreto_de(p["uri"])
    import time
    dos_pasos.activar(ana["id"], dos_pasos.codigo(s, int(time.time()) // 30))
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    r = c.post("/login", data={"usuario": "ana@example.com", "password": "clave-larga-ana"})
    assert r.status_code == 303 and r.headers["location"] == "/login?paso=codigo"
    assert auth.COOKIE not in r.cookies and "aria_2p" in r.cookies          # aún sin sesión
    assert c.get("/api/info").status_code == 401
    r = c.post("/login/codigo", data={"codigo": "000000"})
    assert r.headers["location"] == "/login?paso=codigo&e=codigo"
    r = c.post("/login/codigo", data={"codigo": dos_pasos.codigo(s, int(time.time()) // 30 + 1)})
    assert r.status_code == 303 and r.headers["location"] == "/" and auth.COOKIE in r.cookies
    sin = TestClient(main.app, base_url=LAN, follow_redirects=False)
    assert sin.post("/login/codigo", data={"codigo": "123456"}).headers["location"] == "/login?e=caducado"


def test_api_ajustes(ana):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(ana))
    assert c.get("/api/2fa").json() == {"activa": False, "recuperacion": 0}
    r = c.post("/api/2fa/preparar").json()
    assert r["qr"].startswith("data:image/png;base64,") and len(r["secreto"].replace(" ", "")) == 32
    assert c.post("/api/2fa/activar", json={"codigo": "1"}).status_code == 400
