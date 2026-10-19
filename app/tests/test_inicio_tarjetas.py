import pytest
from fastapi.testclient import TestClient

from aria import auth, main, usuarios


LAN = "https://192.168.1.50"


@pytest.fixture
def ana():
    return usuarios.crear("ana-inicio@example.com", "Ana", "usuario", "clave-larga-ana")


def cliente(usuario):
    c = TestClient(main.app, base_url=LAN)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(usuario))
    return c


def test_tarjetas_aisladas_y_validan_ids(ana):
    otro = usuarios.crear("otro@example.com", "Otro", "usuario", "clave-larga-otro")
    a, b = cliente(ana), cliente(otro)
    assert a.get("/api/inicio/tarjetas").json() == {"orden": [], "ocultas": []}
    assert a.put("/api/inicio/tarjetas", json={"orden": ["finanzas", "tiempo"], "ocultas": ["luz"]}).status_code == 200
    assert a.get("/api/inicio/tarjetas").json() == {"orden": ["finanzas", "tiempo"], "ocultas": ["luz"]}
    assert b.get("/api/inicio/tarjetas").json() == {"orden": [], "ocultas": []}
    assert a.put("/api/inicio/tarjetas", json={"orden": ["inventada"], "ocultas": []}).status_code == 400


def test_tarjetas_sin_sesion_y_csrf():
    anonimo = TestClient(main.app, base_url=LAN, follow_redirects=False)
    assert anonimo.get("/api/inicio/tarjetas").status_code == 401
    admin = usuarios.por_identificador("admin")
    c = cliente(admin)
    assert c.put("/api/inicio/tarjetas", json={"orden": [], "ocultas": []},
                 headers={"Origin": "https://web-atacante.example"}).status_code == 403
