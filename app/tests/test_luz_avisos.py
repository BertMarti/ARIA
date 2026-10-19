from datetime import datetime

import asyncio

import pytest

from aria import avisos, luz, tiempo


@pytest.fixture(autouse=True)
def _sin_espera(monkeypatch):
    monkeypatch.setattr(avisos, "_luz_reintento", 0.0)
    monkeypatch.setattr(avisos, "_luz_hoy_reintento", 0.0)


@pytest.fixture
def admin():
    avisos.iniciar()
    return {"id": 1}      # el administrador que crea el entorno de pruebas


def correr(c):
    return asyncio.run(c)


def serie():
    return [{"hora": h, "precio": 0.08 if 13 <= h < 16 else 0.21 if 19 <= h < 22 else 0.12} for h in range(24)]


def activar_luz(admin):
    avisos.guardar_ajustes(admin["id"], {"tipos": {"luz": True}})


async def falso_emitir(tipo, severidad, texto, enlace="", destinatarios=None, **kw):
    falso_emitir.envios.append((tipo, texto, destinatarios))
    return []


def preparar(monkeypatch):
    falso_emitir.envios = []
    monkeypatch.setattr(avisos, "emitir", falso_emitir)
    monkeypatch.setattr(luz, "precios", lambda dia=None: asyncio.sleep(0, result=serie()))
    monkeypatch.setattr(luz, "activo", lambda: True)


def test_aviso_manana_una_vez_por_usuario(admin, monkeypatch):
    preparar(monkeypatch)
    activar_luz(admin)
    ref = datetime(2026, 10, 17, 21, 0, tzinfo=tiempo.zona())
    assert correr(avisos.luz_de_manana(ref))
    assert not correr(avisos.luz_de_manana(ref))
    assert len(falso_emitir.envios) == 1
    assert "13:00 a 16:00" in falso_emitir.envios[0][1]


def test_aviso_manana_no_se_emite_desactivado(admin, monkeypatch):
    preparar(monkeypatch)
    avisos.guardar_ajustes(admin["id"], {"tipos": {"luz": False}})
    ref = datetime(2026, 10, 17, 21, 0, tzinfo=tiempo.zona())
    assert not correr(avisos.luz_de_manana(ref))
    assert falso_emitir.envios == []


def test_aviso_manana_reintenta_si_no_hay_precios(admin, monkeypatch):
    activar_luz(admin)
    llamadas = []

    async def precios(dia=None):
        llamadas.append(dia)
        if len(llamadas) == 1:
            raise luz.LuzError("no publicado")
        return serie()

    monkeypatch.setattr(avisos, "emitir", falso_emitir)
    falso_emitir.envios = []
    monkeypatch.setattr(luz, "precios", precios)
    monkeypatch.setattr(luz, "activo", lambda: True)
    ref = datetime(2026, 10, 17, 21, 0, tzinfo=tiempo.zona())
    assert not correr(avisos.luz_de_manana(ref))
    assert not correr(avisos.luz_de_manana(ref.replace(minute=5)))   # espera 15 minutos antes de volver a mirar
    monkeypatch.setattr(avisos, "_luz_reintento", 0.0)
    assert correr(avisos.luz_de_manana(ref.replace(minute=20)))
    assert len(llamadas) == 2


def test_aviso_inicio_franja_una_vez(admin, monkeypatch):
    preparar(monkeypatch)
    activar_luz(admin)
    ref = datetime(2026, 10, 17, 13, 0, tzinfo=tiempo.zona())
    assert correr(avisos.luz_inicio_franja(ref))
    assert not correr(avisos.luz_inicio_franja(ref.replace(minute=20)))
    assert "hasta las 16:00" in falso_emitir.envios[0][1]


def test_avisos_luz_apagados(admin, monkeypatch):
    preparar(monkeypatch)
    activar_luz(admin)
    monkeypatch.setattr(luz, "activo", lambda: False)
    ref = datetime(2026, 10, 17, 21, 0, tzinfo=tiempo.zona())
    assert not correr(avisos.luz_de_manana(ref))
    assert not correr(avisos.luz_inicio_franja(ref))
    assert falso_emitir.envios == []
