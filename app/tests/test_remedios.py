import asyncio

import pytest

from aria import config, remedios


def test_clave_y_huella_estables():
    h = {"tipo": "servicio_riesgo", "ip": "192.168.1.50", "titulo": "VNC", "detalle": "5900"}
    assert remedios.clave(h) == remedios.clave(dict(h))
    assert remedios.huella(h) == remedios.huella(dict(h))
    assert remedios.clave(h) != remedios.clave({**h, "titulo": "Otro"})


def test_aceptar_valida_motivo_y_dias():
    remedios.iniciar()
    h = {"tipo": "info", "ip": "192.168.1.50", "titulo": "X", "detalle": "Y"}
    with pytest.raises(ValueError):
        remedios.aceptar(remedios.clave(h), remedios.huella(h), "no", 90, 1)
    with pytest.raises(ValueError):
        remedios.aceptar(remedios.clave(h), remedios.huella(h), "motivo válido", 7, 1)
    remedios.aceptar(remedios.clave(h), remedios.huella(h), "motivo válido", 30, 1)
    assert remedios.estado(h)["estado"] == "aceptado"
    assert remedios.estado({**h, "detalle": "ha cambiado"}) is None


def test_vnc_pi_es_guia_sin_acciones_peligrosas(monkeypatch):
    monkeypatch.setattr(config, "LAN_IP", "192.168.1.50")
    h = {"tipo": "servicio_riesgo", "ip": "192.168.1.50", "titulo": "VNC", "detalle": "Puerto 5900/tcp"}
    r = remedios.remedio(h)
    assert r["modo"] == "guia" and not r["acciones"] and r["comprobar"]


def test_aplicar_rechaza_accion_desconocida():
    h = {"tipo": "info", "ip": "192.168.1.50", "titulo": "X", "detalle": "Y"}
    with pytest.raises(ValueError):
        asyncio.run(remedios.aplicar(h, "borrar_sistema", 1))
