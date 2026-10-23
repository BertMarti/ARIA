"""Hogar: posiciones guardadas de las cámaras con motor (Tapo C520WS). Sin red: un motor falso que apunta las órdenes."""
import asyncio
import time

import pytest

from aria import api_hogar, hogar_tapo, tools, usuarios
from test_hogar import PASS_FALSA, CamaraFalsa, _tapo, cliente, limpio  # noqa: F401 - la fixture se reutiliza

IP = "192.168.1.30"


class Motor:
    """PanTilt de python-kasa: `get_presets` con listas paralelas, `goto_preset`, `save_preset` y `move`."""
    def __init__(self, presets=None):
        self.presets = [list(p) for p in (presets or [])]   # [id, nombre, read_only]
        self.llamadas = []
        self.falla = False

    async def get_presets(self):
        if self.falla:
            raise RuntimeError("sin respuesta")
        p = {"id": [x[0] for x in self.presets], "name": [x[1] for x in self.presets], "read_only": [x[2] for x in self.presets],
             "position_pan": ["0"] * len(self.presets), "position_tilt": ["0"] * len(self.presets), "position_zoom": ["0"] * len(self.presets)}
        return {"getPresetConfig": {"preset": {"preset": p}}}

    async def goto_preset(self, preset_id):
        self.llamadas.append(("ir", preset_id))
        return {"error_code": 0}

    async def save_preset(self, name):
        self.llamadas.append(("guardar", name))
        self.presets.append([str(max([int(x[0]) for x in self.presets] + [0]) + 1), name, "0"])
        return {"error_code": 0}

    async def move(self, *, pan, tilt):
        self.llamadas.append(("mover", pan, tilt))


class CamaraConMotor(CamaraFalsa):
    def __init__(self, presets=None):
        super().__init__()
        self.motor = Motor(presets)
        self.modules["PanTilt"] = self.motor
        self.crudas = []
        self.error_borrar = None

    async def _raw_query(self, peticion):
        self.crudas.append(peticion)
        if self.error_borrar is not None:
            return {"error_code": self.error_borrar}
        ids = peticion["deletePreset"]["preset"]["remove_preset"]["id"]
        self.motor.presets = [p for p in self.motor.presets if p[0] not in ids]
        return {"error_code": 0}


def _camara(monkeypatch, presets=None):
    camara = CamaraConMotor(presets)
    _tapo(monkeypatch, camara)
    return camara


# --- Módulo ------------------------------------------------------------------------------------------------------
def test_parsea_get_presets_vacio_y_con_fijas():
    assert hogar_tapo._parsear_posiciones({"getPresetConfig": {"preset": {"preset": {"id": [], "name": [], "read_only": []}}}}) == []
    assert hogar_tapo._parsear_posiciones({}) == [] and hogar_tapo._parsear_posiciones(None) == []
    lista = hogar_tapo._parsear_posiciones({"getPresetConfig": {"preset": {"preset": {
        "id": ["1", "2", 3], "name": ["Puerta", " Jardín ", None], "read_only": ["1", "0"]}}}})
    assert lista == [{"id": "1", "nombre": "Puerta", "fija": True}, {"id": "2", "nombre": "Jardín", "fija": False},
                     {"id": "3", "nombre": "Posición 3", "fija": False}]
    assert hogar_tapo._parsear_posiciones({"preset": {"preset": {"id": ["7"], "name": ["x"]}}}) == [{"id": "7", "nombre": "x", "fija": False}]


def test_lista_va_y_guarda_posiciones(monkeypatch):
    camara = _camara(monkeypatch, [("1", "Puerta", "1"), ("2", "Jardín", "0")])
    assert asyncio.run(hogar_tapo.posiciones(IP)) == [{"id": "1", "nombre": "Puerta", "fija": True}, {"id": "2", "nombre": "Jardín", "fija": False}]
    asyncio.run(hogar_tapo.ir_a_posicion(IP, "2"))
    assert camara.motor.llamadas[-1] == ("ir", "2")
    with pytest.raises(hogar_tapo.TapoError, match="no encontrada"):
        asyncio.run(hogar_tapo.ir_a_posicion(IP, "9"))                   # id que la cámara no tiene
    nuevas = asyncio.run(hogar_tapo.guardar_posicion(IP, "  Ventana "))
    assert camara.motor.llamadas[-1] == ("guardar", "Ventana") and nuevas[-1] == {"id": "3", "nombre": "Ventana", "fija": False}


def test_guardar_valida_nombre_limite_y_repetidos(monkeypatch):
    camara = _camara(monkeypatch, [("1", "Puerta", "0")])
    for malo in ("", "   ", "x" * 31):
        with pytest.raises(hogar_tapo.TapoError, match="nombre"):
            asyncio.run(hogar_tapo.guardar_posicion(IP, malo))
    with pytest.raises(hogar_tapo.TapoError, match="Ya existe"):
        asyncio.run(hogar_tapo.guardar_posicion(IP, "puerta"))             # mismo nombre, otra caja
    camara.motor.presets = [(str(i), f"p{i}", "0") for i in range(1, 9)]
    with pytest.raises(hogar_tapo.TapoError, match="Ya hay 8 posiciones"):
        asyncio.run(hogar_tapo.guardar_posicion(IP, "otra"))
    assert not any(x[0] == "guardar" for x in camara.motor.llamadas)      # nada llegó a la cámara


def test_borrar_usa_la_orden_cruda_y_respeta_las_fijas(monkeypatch):
    camara = _camara(monkeypatch, [("1", "Puerta", "1"), ("2", "Jardín", "0")])
    with pytest.raises(hogar_tapo.TapoError, match="fija"):
        asyncio.run(hogar_tapo.borrar_posicion(IP, "1"))
    with pytest.raises(hogar_tapo.TapoError, match="no encontrada"):
        asyncio.run(hogar_tapo.borrar_posicion(IP, "5"))
    assert camara.crudas == []
    assert asyncio.run(hogar_tapo.borrar_posicion(IP, "2")) == [{"id": "1", "nombre": "Puerta", "fija": True}]
    assert camara.crudas == [{"deletePreset": {"preset": {"remove_preset": {"id": ["2"]}}}}]
    camara.motor.presets.append(["3", "Mesa", "0"])
    camara.error_borrar = -40401
    with pytest.raises(hogar_tapo.TapoError, match="-40401"):            # la cámara contesta con error
        asyncio.run(hogar_tapo.borrar_posicion(IP, "3"))


def test_solo_camaras_conocidas_con_motor_y_sin_respuesta_se_olvida_la_conexion(monkeypatch):
    camara = _camara(monkeypatch)
    with pytest.raises(hogar_tapo.TapoError, match="no encontrada"):
        asyncio.run(hogar_tapo.posiciones("192.168.1.99"))
    camara.motor.falla = True
    hogar_tapo._conexiones[IP] = camara
    with pytest.raises(hogar_tapo.TapoError, match="no ha respondido"):
        asyncio.run(hogar_tapo.posiciones(IP))
    assert IP not in hogar_tapo._conexiones
    _tapo(monkeypatch, CamaraFalsa())                                      # sin PanTilt
    with pytest.raises(hogar_tapo.TapoError, match="no se puede mover"):
        asyncio.run(hogar_tapo.posiciones(IP))


# --- API ---------------------------------------------------------------------------------------------------------
def test_api_posiciones_admin(monkeypatch):
    camara = _camara(monkeypatch, [("1", "Puerta", "1")])
    c = cliente(usuarios.por_identificador("admin"))
    assert c.get("/api/hogar/camaras/posiciones?ip=" + IP).json() == {"posiciones": [{"id": "1", "nombre": "Puerta", "fija": True}]}
    r = c.post("/api/hogar/camaras/posiciones", json={"ip": IP, "nombre": "Jardín"})
    assert r.status_code == 200 and [p["nombre"] for p in r.json()["posiciones"]] == ["Puerta", "Jardín"]
    assert c.post("/api/hogar/camaras/posiciones", json={"ip": IP, "nombre": "jardin"}).status_code == 200   # con acento es otro nombre
    assert c.post("/api/hogar/camaras/posiciones", json={"ip": IP, "nombre": "JARDÍN"}).status_code == 400
    assert c.post("/api/hogar/camaras/posiciones", json={"ip": IP, "nombre": 5}).status_code == 400
    assert c.post("/api/hogar/camaras/posiciones", json={"ip": IP, "nombre": ""}).status_code == 400
    assert c.post("/api/hogar/camaras/posiciones/ir", json={"ip": IP, "id": "2"}).json() == {"ok": True}
    assert camara.motor.llamadas[-1] == ("ir", "2")
    for malo in ({"ip": IP, "id": 2}, {"ip": IP, "id": "abc"}, {"ip": IP, "id": "1" * 11}, {"ip": IP}, [1]):
        assert c.post("/api/hogar/camaras/posiciones/ir", json=malo).status_code == 400
    assert c.post("/api/hogar/camaras/posiciones/ir", json={"ip": IP, "id": "77"}).status_code == 400
    assert c.post("/api/hogar/camaras/posiciones/ir", json={"ip": "192.168.1.99", "id": "1"}).status_code == 400
    assert c.delete("/api/hogar/camaras/posiciones?ip=" + IP + "&id=1").status_code == 400                      # fija
    assert c.delete("/api/hogar/camaras/posiciones?ip=" + IP + "&id=x").status_code == 400
    r = c.delete("/api/hogar/camaras/posiciones?ip=" + IP + "&id=2")
    assert r.status_code == 200 and [p["id"] for p in r.json()["posiciones"]] == ["1", "3"]
    assert c.get("/api/hogar/camaras/posiciones?ip=192.168.1.99").status_code == 400
    camara.motor.falla = True
    assert c.get("/api/hogar/camaras/posiciones?ip=" + IP).status_code == 502
    assert PASS_FALSA not in c.get("/api/hogar/camaras/posiciones?ip=" + IP).text


def test_api_posiciones_solo_admin_incluso_con_ver_camaras(monkeypatch):
    camara = _camara(monkeypatch, [("1", "Puerta", "0")])
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    for quien in (ana, usuarios.actualizar(ana["id"], ver_camaras=True)):
        c = cliente(quien)
        assert c.get("/api/hogar/camaras/posiciones?ip=" + IP).status_code == 403
        assert c.post("/api/hogar/camaras/posiciones", json={"ip": IP, "nombre": "x"}).status_code == 403
        assert c.post("/api/hogar/camaras/posiciones/ir", json={"ip": IP, "id": "1"}).status_code == 403
        assert c.delete("/api/hogar/camaras/posiciones?ip=" + IP + "&id=1").status_code == 403
    assert camara.motor.llamadas == [] and camara.crudas == []


def test_api_posiciones_limites_por_persona(monkeypatch):
    _camara(monkeypatch, [("1", "Puerta", "0")])
    admin = usuarios.por_identificador("admin")
    c = cliente(admin)
    ahora = time.monotonic()
    api_hogar._acciones[(admin["id"], "mover")] = [ahora] * 60                 # mismo cupo que el pad de movimiento
    assert c.post("/api/hogar/camaras/posiciones/ir", json={"ip": IP, "id": "1"}).status_code == 429
    assert c.post("/api/hogar/camaras/posiciones", json={"ip": IP, "nombre": "x"}).status_code == 200   # otro cupo
    api_hogar._acciones[(admin["id"], "accion")] = [ahora] * 30
    assert c.post("/api/hogar/camaras/posiciones", json={"ip": IP, "nombre": "y"}).status_code == 429
    assert c.delete("/api/hogar/camaras/posiciones?ip=" + IP + "&id=1").status_code == 429
    assert c.get("/api/hogar/camaras/posiciones?ip=" + IP).status_code == 200                           # leer no gasta cupo
    otro = usuarios.crear("otro@example.com", "Otro", "admin", "clave-larga-otro")
    assert cliente(otro).post("/api/hogar/camaras/posiciones/ir", json={"ip": IP, "id": "1"}).status_code == 200


# --- Herramienta del chat -----------------------------------------------------------------------------------------
def test_herramienta_camara_posicion(monkeypatch):
    camara = _camara(monkeypatch, [("1", "Puerta", "0"), ("2", "Jardín trasero", "0")])
    assert asyncio.run(tools.camara_posicion("JARDIN")) == "He movido la cámara Jardín a la posición «Jardín trasero»."
    assert camara.motor.llamadas[-1] == ("ir", "2")
    assert asyncio.run(tools.camara_posicion("puerta", "jardin")).endswith("«Puerta».")
    assert camara.motor.llamadas[-1] == ("ir", "1")
    r = asyncio.run(tools.camara_posicion("sofá"))
    assert "no tiene ninguna posición llamada «sofá»" in r and "Puerta, Jardín trasero" in r
    assert "con ese nombre" in asyncio.run(tools.camara_posicion("puerta", "cocina"))
    assert len(camara.motor.llamadas) == 2
    assert "camara_posicion" not in tools.permitidas("usuario") and "camara_posicion" in tools.permitidas("admin")
    assert "camara_posicion" not in tools.RUTINAS
    assert "camara_posicion" in tools.relevantes("gira la cámara a la posición puerta")
    assert "camara_posicion" in tools.relevantes("apunta al jardín")
    assert "camara_posicion" not in tools.relevantes("tapa la cámara")


def test_herramienta_camara_posicion_sin_motor(monkeypatch):
    _tapo(monkeypatch, CamaraFalsa())
    assert asyncio.run(tools.camara_posicion("puerta")) == "No he encontrado ninguna cámara con motor."
