"""Pruebas de reglas, aislamiento, acciones y deduplicación de automatizaciones."""
import asyncio
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from aria import auth, avisos, automatizaciones, config, main, sistema, usuarios
from aria import db
from aria import tiempo

LAN = "https://192.168.1.50"


def cliente(u):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


@pytest.fixture(autouse=True)
def inicializar():
    automatizaciones.iniciar()


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def datos(**cambios):
    base = {"nombre": "Avisar", "disparador": {"tipo": "aviso", "aviso": "servicios"},
            "condiciones": {}, "acciones": [{"tipo": "avisar", "texto": "Ha ocurrido algo."}]}
    base.update(cambios)
    return base


def test_crud_filtra_por_usuario_y_rechaza_acciones_desconocidas(admin, ana):
    r = automatizaciones.crear(admin["id"], datos())
    assert automatizaciones.listar(ana["id"]) == []
    assert automatizaciones.obtener(ana["id"], r["id"]) is None
    with pytest.raises(automatizaciones.AutomatizacionError):
        automatizaciones.crear(admin["id"], datos(acciones=[{"tipo": "reiniciar", "texto": "no"}]))


def test_evento_ejecuta_accion_y_anti_bucle(admin, monkeypatch):
    r = automatizaciones.crear(admin["id"], datos())
    recibidos = []

    async def canal(uid, aviso):
        recibidos.append(aviso["texto"])
        return True

    monkeypatch.setattr(avisos, "_CANALES", {"telegram": canal})
    monkeypatch.setattr(avisos, "en_silencio", lambda *a, **k: False)  # que no dependa de la hora real
    asyncio.run(automatizaciones.evento("servicios", {"tipo": "servicios"}))
    asyncio.run(automatizaciones.evento("servicios", {"tipo": "servicios"}))
    assert recibidos == ["Ha ocurrido algo."]
    assert automatizaciones.registro(admin["id"])[0]["resultado"] == "ok"


def test_hora_y_umbral(monkeypatch, admin):
    ahora = datetime(2026, 10, 8, 7, 30, tzinfo=tiempo.zona())
    automatizaciones.crear(admin["id"], datos(disparador={"tipo": "hora", "hora": "07:30", "dias": []}))
    automatizaciones.crear(admin["id"], datos(disparador={"tipo": "umbral", "metrica": "temperatura", "operador": ">", "valor": 75}))
    monkeypatch.setattr(sistema, "temperatura", lambda: 80.0)
    monkeypatch.setattr(automatizaciones, "_accion", lambda *a: asyncio.sleep(0))
    assert len(asyncio.run(automatizaciones.tick(ahora.timestamp()))) == 2


def test_condiciones_franja_y_desconocido(admin):
    r = automatizaciones.crear(admin["id"], datos(condiciones={"desde": "00:00", "hasta": "07:00", "dispositivo_desconocido": True}))
    ref = datetime(2026, 10, 8, 6, 0, tzinfo=tiempo.zona())
    assert automatizaciones._condiciones_ok(r, {"dispositivo_desconocido": True}, ref)
    assert not automatizaciones._condiciones_ok(r, {"dispositivo_desconocido": False}, ref)


def test_usuario_recibe_403_y_no_hay_idor(admin, ana):
    aid = automatizaciones.crear(admin["id"], datos())["id"]
    c = cliente(ana)
    assert c.get("/api/automatizaciones").status_code == 403
    assert c.patch(f"/api/automatizaciones/{aid}", json={"activa": False}).status_code == 403


def test_limite_de_veinte(admin):
    for n in range(20): automatizaciones.crear(admin["id"], datos(nombre=f"Regla {n}"))
    with pytest.raises(automatizaciones.AutomatizacionError): automatizaciones.crear(admin["id"], datos())
