"""Recibos fijos: detección local, avisos por usuario y ruta protegida."""
from datetime import date

import pytest

from aria import avisos, finanzas, main, usuarios
from fastapi.testclient import TestClient
from tests.test_permisos import LAN, cliente_de


def _meses():
    hoy = date.today().replace(day=1)
    out = []
    for i in range(4):
        m = hoy.month - 3 + i
        y = hoy.year + (m - 1) // 12
        out.append(f"{y:04d}-{(m - 1) % 12 + 1:02d}")
    return out


@pytest.fixture
def ana():
    return usuarios.crear("ana-fijos@example.com", "Ana", "usuario", "clave-larga-ana")


def _netflix(uid):
    for i, mes in enumerate(_meses()):
        importe = -12.99 if i < 2 else -15.99
        finanzas.registrar(uid, mes + "-05", "RECIBO NETFLIX.COM", importe)


@pytest.mark.asyncio
async def test_detecta_y_avisa_una_vez(ana):
    _netflix(ana["id"])
    d = finanzas.gastos_fijos(ana["id"])
    assert len(d["fijos"]) == 1
    assert d["fijos"][0]["ultimo_importe"] == 1599
    assert d["fijos"][0]["cambio_pct"] > 10
    await finanzas.avisar_gastos_fijos(ana["id"])
    await finanzas.avisar_gastos_fijos(ana["id"])
    assert len(avisos.listar(ana["id"])["avisos"]) == 1


def test_ruido_no_se_detecta(ana):
    uid = ana["id"]
    finanzas.registrar(uid, _meses()[0] + "-05", "Compra única", -20)
    for i, mes in enumerate(_meses()[1:]):
        finanzas.registrar(uid, mes + "-20", "Importes distintos", -(i + 1) * 100)
    assert finanzas.gastos_fijos(uid)["fijos"] == []


def test_aislamiento_por_usuario(ana):
    admin = usuarios.por_identificador("admin")
    _netflix(admin["id"])
    assert finanzas.gastos_fijos(ana["id"])["fijos"] == []


def test_ruta_fijos_protegida(ana):
    assert cliente_de(ana).get("/api/finanzas/fijos").status_code == 200
    assert TestClient(main.app, base_url=LAN, follow_redirects=False).get("/api/finanzas/fijos").status_code in (401, 303)


def test_marca_de_recibo_avisado_dura_mas_de_una_semana(monkeypatch):
    import time as _t
    from aria import avisos
    avisos._anotar_enviado("fijo:1:netflix:2026-10", "fijos", 45)
    # Otra clave de briefing purga las de su familia, no las de recibos fijos.
    real = _t.time
    monkeypatch.setattr(avisos.time, "time", lambda: real() + 10 * 86400)
    avisos._anotar_enviado("briefing:x", "briefing", 7)
    assert avisos._ya_enviado("fijo:1:netflix:2026-10")


def test_avisos_personales_no_copian_el_texto_a_las_automatizaciones(monkeypatch):
    import asyncio
    from aria import automatizaciones, avisos
    vistos = []

    async def evento(tipo, datos):
        vistos.append(datos)
    monkeypatch.setattr(automatizaciones, "evento", evento)
    asyncio.run(avisos.emitir("fijos", "aviso", "Netflix ha subido de 12,99 € a 15,99 €.", "finanzas", []))
    assert vistos and vistos[0]["texto"] == ""
