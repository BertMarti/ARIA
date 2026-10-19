"""Pruebas unitarias del servicio, sin cámaras reales."""
import asyncio

import pytest

import servicio


def test_camara_rechaza_identificador_desconocido(monkeypatch):
    monkeypatch.setattr(servicio, "CAMARAS", ["192.168.1.30"])
    monkeypatch.setattr(servicio, "_candados", {"c1": asyncio.Lock()})
    with pytest.raises(servicio.HTTPException) as error:
        servicio.camara("c2")
    assert error.value.status_code == 404


def test_duracion_y_clave_no_permiten_rangos_arbitrarios():
    with pytest.raises(servicio.HTTPException):
        servicio._numero("no", "Inicio")
    assert servicio._clave("c1", 10, 20) != servicio._clave("c2", 10, 20)


def test_recortar_cache_borra_los_mas_antiguos(monkeypatch, tmp_path):
    monkeypatch.setattr(servicio, "CACHE", tmp_path)
    import os
    monkeypatch.setattr(servicio, "CACHE_MAX_BYTES", 1500)
    viejo, nuevo = tmp_path / "a.mp4", tmp_path / "b.mp4"
    viejo.write_bytes(b"a" * 1000)
    nuevo.write_bytes(b"b" * 1000)
    os.utime(viejo, (1, 1))                       # el que lleva más tiempo sin usarse
    servicio._recortar_cache()
    assert not viejo.exists() and nuevo.exists()   # 2000 > 1500: sobra uno, el más viejo


# --- /eventos ------------------------------------------------------------------------------------------------------
class _CamaraFalsa:
    """pytapo de mentira: la hora de la cámara va 100 s por detrás de la real."""
    def __init__(self, eventos=None, correccion=100):
        self.eventos, self.correccion, self.pedidos = eventos or [], correccion, []

    def getTimeCorrection(self):
        return self.correccion

    def getEvents(self, inicio, fin):
        self.pedidos.append((inicio, fin))
        return self.eventos


def _servicio(monkeypatch, camara):
    from starlette.testclient import TestClient
    monkeypatch.setattr(servicio, "CAMARAS", ["192.168.1.30"])
    monkeypatch.setattr(servicio, "PASSWORD", "clave-de-prueba")
    monkeypatch.setattr(servicio, "_candados", {"c1": asyncio.Lock()})
    monkeypatch.setattr(servicio, "_cliente", lambda ip: camara)
    return TestClient(servicio.app)


def test_eventos_devuelve_detecciones_en_hora_real_y_pregunta_en_hora_de_camara(monkeypatch):
    import time
    ahora = int(time.time())
    camara = _CamaraFalsa([
        {"start_time": ahora - 600, "end_time": ahora - 580, "alarm_type": 6, "events_1": 34},   # pytapo ya los corrige
        {"start_time": ahora - 900, "end_time": ahora - 890, "alarm_type": 1},
        {"start_time": "mal", "end_time": ahora},                                              # basura: se ignora
    ])
    c = _servicio(monkeypatch, camara)
    r = c.get("/eventos", params={"cam": "c1", "desde": ahora - 3600, "hasta": ahora})
    assert r.status_code == 200
    assert r.json() == {"eventos": [{"inicio": ahora - 900, "fin": ahora - 890, "tipo": 1},
                                    {"inicio": ahora - 600, "fin": ahora - 580, "tipo": 6}]}
    assert camara.pedidos == [(ahora - 3600 - 100, ahora - 100)]           # en la hora de la cámara (real - corrección)


def test_eventos_valida_camara_e_intervalo(monkeypatch):
    import time
    ahora = int(time.time())
    camara = _CamaraFalsa()
    c = _servicio(monkeypatch, camara)
    assert c.get("/eventos", params={"cam": "c9", "desde": ahora - 60, "hasta": ahora}).status_code == 404
    assert c.get("/eventos", params={"cam": "c1", "desde": "x", "hasta": ahora}).status_code == 400
    assert c.get("/eventos", params={"cam": "c1", "desde": ahora, "hasta": ahora}).status_code == 400       # hasta <= desde
    assert c.get("/eventos", params={"cam": "c1", "desde": ahora - 3601, "hasta": ahora}).status_code == 400  # más de una hora
    assert c.get("/eventos", params={"cam": "c1", "desde": ahora, "hasta": ahora + 300}).status_code == 400   # en el futuro
    assert camara.pedidos == []                                             # nada de eso llegó a la cámara
    assert c.get("/eventos", params={"cam": "c1", "desde": ahora - 60, "hasta": ahora + 60}).status_code == 200


def test_eventos_sin_hora_o_con_camara_lenta(monkeypatch):
    import time
    ahora = int(time.time())
    c = _servicio(monkeypatch, _CamaraFalsa(correccion=False))
    assert c.get("/eventos", params={"cam": "c1", "desde": ahora - 60, "hasta": ahora}).status_code == 502

    def lenta(ip, desde, hasta):
        raise asyncio.TimeoutError
    monkeypatch.setattr(servicio, "_eventos", lenta)
    r = c.get("/eventos", params={"cam": "c1", "desde": ahora - 60, "hasta": ahora})
    assert r.status_code == 504 and "tardado" in r.json()["error"]
