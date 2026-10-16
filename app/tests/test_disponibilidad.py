"""Cálculos y aislamiento del historial de disponibilidad."""
import asyncio
import pytest

from aria import auth, disponibilidad, main, usuarios
from fastapi.testclient import TestClient


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def cliente(u):
    c = TestClient(main.app, base_url="https://192.168.1.50", follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def test_porcentaje_caidas_y_mas_larga(admin):
    base = 1_700_000_000
    for ts, ok in ((0, 1), (60, 0), (120, 0), (180, 1), (240, 0)):
        disponibilidad.registrar("ARIA", base + ts, ok, 10, "fallo" if not ok else "")
    d = disponibilidad.resumen(1, base + 300)
    fila = next(x for x in d["servicios"] if x["servicio"] == "ARIA")
    assert fila["porcentaje"] == 40.0 and fila["caidas"] == 2   # 2 de 5 muestras bien
    i = disponibilidad.incidentes(1, base + 300)
    assert i[0]["duracion"] == 120 and i[0]["detalle"] == "fallo"


def test_agregado_horario_y_purga(admin):
    base = 1_600_000_000
    disponibilidad.registrar("ARIA", base, True, 8)
    disponibilidad.registrar("ARIA", base + 60, False, None, "caído")
    disponibilidad.purgar(base + 31 * 86400)
    from aria import db
    with db._con() as con:
        assert con.execute("SELECT count(*) FROM disponibilidad").fetchone()[0] == 0
        assert con.execute("SELECT muestras, buenas FROM disponibilidad_hora").fetchone()[:2] == (2, 1)


def test_usuario_no_ve_el_historial(ana):
    assert cliente(ana).get("/api/disponibilidad").status_code == 403


def test_fallo_de_registro_no_rompe_tick(admin, monkeypatch):
    async def roto(*args):
        raise RuntimeError("sqlite ocupado")
    monkeypatch.setattr(disponibilidad, "ciclo", roto)
    asyncio.run(main.avisos.tick(1_900_000_000))
