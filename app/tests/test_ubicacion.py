import asyncio
import time
from contextlib import closing

from aria import avisos_meteo, db, ubicacion, usuarios


def _usuario():
    ubicacion.iniciar()
    return usuarios.crear("geo@example.test", "Geo", "usuario")["id"]


def test_provincias_espanolas():
    assert {k: ubicacion.PROVINCIAS[k] for k in ("J", "BU", "M", "B", "PM", "GC", "TF", "CE", "ML")} == {
        "J": "23", "BU": "09", "M": "28", "B": "08", "PM": "07", "GC": "35", "TF": "38", "CE": "51", "ML": "52"}


def test_fijar_redondea_y_caduca(monkeypatch):
    uid = _usuario()
    async def inversa(lat, lon):
        return _inversa()
    monkeypatch.setattr(ubicacion.mapas, "inversa", inversa)
    asyncio.run(ubicacion.fijar(uid, 42.351, -3.701))
    fila = ubicacion.actual(uid)
    assert fila["lat"] == 42.35 and fila["lon"] == -3.7 and fila["origen"] == "dispositivo"
    with closing(db._con()) as con, con:
        con.execute("UPDATE ubicaciones SET ts=? WHERE user_id=?", (time.time() - 12 * 3600 - 1, uid))
    assert ubicacion.actual(uid) is None


def test_identifier_filtra_provincia_y_traduce_evento():
    xml = '<feed xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2"><entry>' \
          '<cap:identifier>x.ES.000000000000.612301</cap:identifier>' \
          '<cap:areaDesc>Morena y Condado</cap:areaDesc><cap:severity>Moderate</cap:severity>' \
          '<cap:event>Moderate rain warning</cap:event></entry></feed>'
    aviso = avisos_meteo.parsear(xml, provincia="23")[0]
    assert aviso["provincia"] == "23" and aviso["evento"] == "lluvia" and aviso["color"] == "amarillo"
    assert avisos_meteo.parsear(xml, provincia="09") == []


def _inversa():
    return {"nombre": "Burgos", "provincia": "ES-BU"}


def test_provincia_de_comunidad_uniprovincial():
    assert ubicacion._provincia("", "ES-MD") == "28" and ubicacion._provincia(None, "ES-AS") == "33"
    assert ubicacion._provincia("ES-BU", "ES-CL") == "09"


def _cliente(rol="usuario", vista=None):
    from fastapi.testclient import TestClient
    from aria import auth, main
    u = usuarios.crear(f"{rol}{vista or ''}@example.test", "Geo", rol, "clave-de-prueba-larga")
    c = TestClient(main.app, base_url="https://192.168.1.50", follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    if vista:
        c.cookies.set(main.VISTA_COOKIE, vista)
    return c, u["id"]


def test_api_nunca_devuelve_coordenadas(monkeypatch):
    from aria import config
    ubicacion.iniciar()
    monkeypatch.setattr(config, "LAT", 40.42); monkeypatch.setattr(config, "LON", -3.7)
    async def inversa(lat, lon):
        return {"nombre": "Burgos", "provincia": "ES-BU", "comunidad": "ES-CL"}
    monkeypatch.setattr(ubicacion.mapas, "inversa", inversa)
    c, uid = _cliente()
    origen = {"Origin": "https://192.168.1.50"}
    r = c.get("/api/ubicacion")
    assert r.status_code == 200 and r.json() == {"origen": "casa", "nombre": "Casa"}
    r = c.post("/api/ubicacion", json={"lat": 42.3439, "lon": -3.6969}, headers=origen)
    assert r.json() == {"origen": "dispositivo", "nombre": "Burgos"}
    assert ubicacion.actual(uid)["provincia"] == "09"
    assert "lat" not in c.get("/api/ubicacion").json()
    assert c.delete("/api/ubicacion", headers=origen).json()["ubicacion"]["origen"] == "casa"
    assert ubicacion.actual(uid)["origen"] == "casa"


def test_vista_de_prueba_no_guarda(monkeypatch):
    ubicacion.iniciar()
    c, uid = _cliente("admin", "visita")
    r = c.post("/api/ubicacion", json={"lat": 42.34, "lon": -3.69}, headers={"Origin": "https://192.168.1.50"})
    assert r.status_code == 200
    with closing(db._con()) as con:
        assert con.execute("SELECT COUNT(*) FROM ubicaciones WHERE user_id=?", (uid,)).fetchone()[0] == 0


def test_ubicacion_requiere_sesion():
    from fastapi.testclient import TestClient
    from aria import main
    r = TestClient(main.app, base_url="https://192.168.1.50", follow_redirects=False).get("/api/ubicacion")
    assert r.status_code in (302, 303, 401, 403)
