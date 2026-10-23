"""Hogar: escenas (varias luces y cámaras de un toque), su herramienta de chat y la escena al llegar de noche."""
import asyncio
import datetime as dt
import time

import pytest

from aria import config, hogar_cache, hogar_govee, hogar_tapo, tools, usuarios
from test_hogar import MOVILES, _vigilancia, cliente, limpio  # noqa: F401 - la fixture se reutiliza

LUCES = [{"id": "AA:01", "nombre": "Despacho", "encendida": False, "color": "#ffffff"},
         {"id": "AA:02", "nombre": "Salón", "encendida": True}]
CAM = "192.168.1.30"


@pytest.fixture
def casa(monkeypatch):
    """Luces y cámaras conocidas (caché) y dobles que apuntan lo que se manda."""
    hogar_cache._datos["luces"] = (time.monotonic(), LUCES)
    hogar_cache._datos["camaras"] = (time.monotonic(), [{"ip": CAM, "nombre": "Pasillo", "privacidad": True}])
    monkeypatch.setattr(config, "TAPO_CAMARAS", [CAM])
    hechos = {"luces": [], "camaras": [], "falla": set()}

    async def cambiar(identificador, encendida=None, brillo=None, color=None):
        if identificador in hechos["falla"]:
            raise hogar_govee.GoveeError("sin conexión")
        hechos["luces"].append((identificador, encendida, brillo, color))
        return {"ok": True}

    async def privacidad(ip, activa):
        hechos["camaras"].append((ip, activa))
        return {}
    async def luces():
        return LUCES
    monkeypatch.setattr(hogar_govee, "cambiar", cambiar)
    monkeypatch.setattr(hogar_govee, "luces", luces)
    monkeypatch.setattr(hogar_govee, "configurado", lambda: True)
    monkeypatch.setattr(hogar_tapo, "privacidad", privacidad)
    yield hechos
    hogar_cache.limpiar()


CINE = {"nombre": "Cine", "icono": "cine", "acciones": [
    {"tipo": "luz", "id": "AA:01", "encendida": True, "brillo": 20, "color": "#3366FF"},
    {"tipo": "luz", "id": "AA:02", "encendida": False},
    {"tipo": "camara", "ip": CAM, "privacidad": True}]}


def test_crear_y_activar_escena(casa):
    from aria import hogar_escenas as he
    e = he.crear(CINE, asyncio.run(he.conocidas()))
    assert e["nombre"] == "Cine" and e["acciones"][0]["color"] == "#3366ff"
    r = asyncio.run(he.ejecutar(e))
    assert r == {"hechas": 3, "fallidas": []}
    assert casa["luces"] == [("AA:01", True, 20, 0x3366FF), ("AA:02", False, None, None)]
    assert casa["camaras"] == [(CAM, True)]


def test_una_luz_que_falla_no_para_la_escena_y_se_nombra(casa):
    from aria import hogar_escenas as he
    casa["falla"].add("AA:01")
    r = asyncio.run(he.ejecutar(he.crear(CINE, asyncio.run(he.conocidas()))))
    assert r == {"hechas": 2, "fallidas": ["Despacho"]} and casa["camaras"] == [(CAM, True)]


@pytest.mark.parametrize("cambio, error", [
    ({"nombre": ""}, "nombre"),
    ({"nombre": "x" * 31}, "nombre"),
    ({"icono": "<script>"}, "Icono"),
    ({"acciones": []}, "acciones"),
    ({"acciones": [{"tipo": "luz", "id": "ZZ:99", "encendida": True}]}, "no está en tu casa"),
    ({"acciones": [{"tipo": "camara", "ip": "192.168.1.99", "privacidad": True}]}, "no está en tu casa"),
    ({"acciones": [{"tipo": "luz", "id": "AA:01", "encendida": True, "brillo": 0}]}, "brillo"),
    ({"acciones": [{"tipo": "luz", "id": "AA:01", "encendida": True, "color": "rojo"}]}, "color"),
    ({"acciones": [{"tipo": "luz", "id": "AA:01", "encendida": "sí"}]}, "enciende"),
    ({"acciones": [{"tipo": "luz", "id": "AA:01", "encendida": True}, {"tipo": "luz", "id": "AA:01", "encendida": False}]}, "una vez"),
    ({"acciones": [{"tipo": "enchufe"}]}, "Acción"),
])
def test_validaciones(casa, cambio, error):
    from aria import hogar_escenas as he
    with pytest.raises(he.EscenaError, match=error):
        he.crear({**CINE, **cambio}, asyncio.run(he.conocidas()))


def test_nombre_unico_sin_mayusculas_y_maximo(casa, monkeypatch):
    from aria import hogar_escenas as he
    he.crear(CINE, asyncio.run(he.conocidas()))
    with pytest.raises(he.EscenaError, match="Ya hay"):
        he.crear({**CINE, "nombre": "cine"}, asyncio.run(he.conocidas()))
    monkeypatch.setattr(he, "MAX_ESCENAS", 2)
    he.crear({**CINE, "nombre": "Noche"}, asyncio.run(he.conocidas()))
    with pytest.raises(he.EscenaError, match="Como mucho"):
        he.crear({**CINE, "nombre": "Fiesta"}, asyncio.run(he.conocidas()))


def test_api_solo_admin_crud_y_activar(casa):
    admin = usuarios.por_identificador("admin")
    c = cliente(admin)
    r = c.post("/api/hogar/escenas", json=CINE)
    assert r.status_code == 200
    eid = r.json()["escena"]["id"]
    assert [e["nombre"] for e in c.get("/api/hogar/escenas").json()["escenas"]] == ["Cine"]
    assert c.put(f"/api/hogar/escenas/{eid}", json={**CINE, "nombre": "Peli"}).json()["escena"]["nombre"] == "Peli"
    assert c.post(f"/api/hogar/escenas/{eid}/activar").json() == {"hechas": 3, "fallidas": []}
    assert c.post("/api/hogar/escenas", json={**CINE, "icono": "x"}).status_code == 400
    assert c.put("/api/hogar/escenas/999", json=CINE).status_code == 404   # tras activar la caché se vació: se vuelve a pedir
    pepa = usuarios.actualizar(usuarios.crear("pepa@example.com", "Pepa", "usuario", "clave-larga-pepa")["id"], ver_camaras=True)
    p = cliente(pepa)
    assert p.get("/api/hogar/escenas").status_code == 403
    assert p.post(f"/api/hogar/escenas/{eid}/activar").status_code == 403
    assert p.delete(f"/api/hogar/escenas/{eid}").status_code == 403
    assert c.delete(f"/api/hogar/escenas/{eid}").json() == {"ok": True}
    assert c.delete(f"/api/hogar/escenas/{eid}").status_code == 404


def test_herramienta_escena(casa):
    from aria import hogar_escenas as he
    assert "Aún no hay escenas" in asyncio.run(tools.escena("cine"))
    he.crear(CINE, asyncio.run(he.conocidas()))
    he.crear({**CINE, "nombre": "Cine de noche"}, asyncio.run(he.conocidas()))
    assert asyncio.run(tools.escena("")) == "Escenas: Cine, Cine de noche."
    assert asyncio.run(tools.escena("CINE")) == "Escena «Cine» activada."           # el nombre exacto gana
    assert "varias" in asyncio.run(tools.escena("ci"))
    assert "No hay ninguna" in asyncio.run(tools.escena("fiesta"))
    assert "escena" not in tools.permitidas("usuario") and "escena" in tools.permitidas("admin")


# --- De noche --------------------------------------------------------------------------------------------------------
def _ts(fecha_hora: str) -> float:
    return dt.datetime.fromisoformat(fecha_hora).replace(tzinfo=dt.timezone.utc).timestamp()


def test_es_de_noche_con_coordenadas(monkeypatch):
    from aria import hogar_escenas as he
    monkeypatch.setattr(config, "LAT", 40.4)    # Madrid
    monkeypatch.setattr(config, "LON", -3.7)
    assert not he.es_de_noche(_ts("2026-06-21T12:00:00"))
    assert he.es_de_noche(_ts("2026-06-21T21:00:00"))      # 23:00 en Madrid en verano
    assert not he.es_de_noche(_ts("2026-06-21T19:00:00"))  # 21:00 en verano aún hay luz
    assert he.es_de_noche(_ts("2026-12-21T17:30:00"))      # 18:30 en invierno ya es de noche
    assert he.es_de_noche(_ts("2026-12-21T06:30:00"))      # 7:30 en invierno aún no ha salido


def test_es_de_noche_sin_coordenadas_usa_horario(monkeypatch):
    from aria import hogar_escenas as he
    monkeypatch.setattr(config, "LAT", None)
    monkeypatch.setattr(config, "LON", None)
    monkeypatch.setattr(config, "TZ", "UTC")
    assert he.es_de_noche(_ts("2026-06-21T22:00:00")) and he.es_de_noche(_ts("2026-06-21T07:00:00"))
    assert not he.es_de_noche(_ts("2026-06-21T12:00:00"))


def test_al_llegar_de_noche_activa_la_escena_elegida(casa, monkeypatch):
    from aria import hogar_escenas as he
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, MOVILES)
    e = he.crear({"nombre": "Bienvenida", "icono": "casa", "acciones": [{"tipo": "luz", "id": "AA:01", "encendida": True, "brillo": 60}]}, asyncio.run(he.conocidas()))
    hv.configurar({"escena_llegada": e["id"]}, MOVILES)
    assert hv.resumen(MOVILES)["escena_llegada"] == e["id"]
    with pytest.raises(ValueError):
        hv.configurar({"escena_llegada": 999}, MOVILES)
    noche = {"v": True}
    monkeypatch.setattr(he, "es_de_noche", lambda ahora=None: noche["v"])
    t = time.time()
    asyncio.run(hv.ciclo(t))
    estado["conectados"] = []
    assert asyncio.run(hv.ciclo(t + 15 * 60)) == "fuera"
    estado["conectados"] = MOVILES[:1]
    assert asyncio.run(hv.ciclo(t + 30 * 60)) == "casa"
    assert ("AA:01", True, 60, None) in casa["luces"] and "Bienvenida" in emitidos[-1][1]
    # De día no se activa
    casa["luces"].clear()
    noche["v"] = False
    estado["conectados"] = []
    asyncio.run(hv.ciclo(t + 50 * 60))
    estado["conectados"] = MOVILES[:1]
    assert asyncio.run(hv.ciclo(t + 60 * 60)) == "casa"
    assert casa["luces"] == [] and "escena" not in emitidos[-1][1]
