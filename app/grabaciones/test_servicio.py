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
    monkeypatch.setattr(servicio, "CACHE_MAX_BYTES", 1)
    primero, segundo = tmp_path / "a.mp4", tmp_path / "b.mp4"
    primero.write_bytes(b"a")
    segundo.write_bytes(b"b" * 1024)
    servicio._recortar_cache()
    assert not primero.exists() and segundo.exists()
