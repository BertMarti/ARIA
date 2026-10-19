"""Insistencia de recordatorios y migración de su tabla."""
import asyncio
from datetime import datetime

import pytest

from aria import avisos, db, recordatorios as rec, tiempo, tools, usuarios

Z = tiempo.zona()
REF = datetime(2026, 10, 7, 10, 0, tzinfo=Z)


@pytest.fixture
def admin():
    rec.iniciar()
    return usuarios.crear("admin-rec@example.com", "Admin", "admin", "clave-larga-admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana-rec@example.com", "Ana", "usuario", "clave-larga-ana")


def correr(c):
    return asyncio.run(c)


def test_reavisa_tres_veces_y_no_mas(admin, monkeypatch):
    avisos_enviados = []

    async def canal(uid, aviso):
        avisos_enviados.append(aviso["texto"])
        return True

    monkeypatch.setattr(avisos, "_CANALES", {"falso": canal})
    r = rec.crear(admin["id"], "tomar la medicación", "en 10 minutos", insistir=True, ref=REF)
    base = r["cuando"]
    assert correr(rec.disparar_vencidos(base)) == [r["id"]]
    for n in range(1, 4):
        assert correr(rec.disparar_vencidos(base + n * 15 * 60)) == [r["id"]]
    assert len(avisos_enviados) == 4
    assert avisos_enviados[1].startswith("Otra vez: ")
    assert correr(rec.disparar_vencidos(base + 4 * 15 * 60)) == []


def test_hecho_corta_y_posponer_reinicia(admin, monkeypatch):
    monkeypatch.setattr(avisos, "_CANALES", {})
    r = rec.crear(admin["id"], "pastilla", "en 10 minutos", insistir=True, ref=REF)
    base = r["cuando"]
    correr(rec.disparar_vencidos(base))
    assert rec.hecho(admin["id"], r["id"])
    assert correr(rec.disparar_vencidos(base + 15 * 60)) == []
    p = rec.crear(admin["id"], "medicamento", "en 10 minutos", insistir=True, ref=REF)
    correr(rec.disparar_vencidos(p["cuando"]))
    aplazado = rec.posponer(admin["id"], p["id"], 10)
    assert aplazado["reintentos"] == 0 and aplazado["estado"] == "pendiente"


def test_repetitivo_avanza_al_marcar_hecho_o_agotar(admin, monkeypatch):
    monkeypatch.setattr(avisos, "_CANALES", {})
    r = rec.crear(admin["id"], "pastilla diaria", "todos los días a las 11", insistir=True, ref=REF)
    base = r["cuando"]
    correr(rec.disparar_vencidos(base))
    rec.hecho(admin["id"], r["id"])
    assert rec.obtener(admin["id"], r["id"])["cuando"] == datetime(2026, 10, 8, 11, tzinfo=Z).timestamp()
    r = rec.crear(admin["id"], "medicación", "todos los días a las 12", insistir=True, ref=REF)
    base = r["cuando"]
    for n in range(4):
        correr(rec.disparar_vencidos(base + n * 15 * 60))
    assert rec.obtener(admin["id"], r["id"])["cuando"] == datetime(2026, 10, 8, 12, tzinfo=Z).timestamp()


def test_herramienta_detecta_pastilla(admin):
    correr(tools.ejecutar("recordatorio", {"texto": "tomar la pastilla", "cuando": "en 10 minutos"},
                          "admin", uid=admin["id"]))
    assert rec.listar(admin["id"])[0]["insistir"]


def test_no_se_puede_marcar_ni_posponer_el_de_otro(admin, ana):
    r = rec.crear(ana["id"], "medicación", "en 10 minutos", insistir=True, ref=REF)
    assert not rec.hecho(admin["id"], r["id"])
    assert rec.posponer(admin["id"], r["id"], 10) is None
    assert rec.obtener(ana["id"], r["id"])["estado"] == "pendiente"


def test_migracion_de_tabla_antigua(admin):
    with db._con() as con, con:
        con.execute("DROP TABLE recordatorios")
        con.execute("CREATE TABLE recordatorios (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
                    "texto TEXT NOT NULL, cuando REAL NOT NULL, repetir TEXT, estado TEXT NOT NULL DEFAULT 'pendiente', "
                    "creado REAL NOT NULL, avisado REAL)")
        con.execute("INSERT INTO recordatorios (user_id, texto, cuando, creado) VALUES (?, ?, ?, ?)",
                    (admin["id"], "antiguo", REF.timestamp(), REF.timestamp()))
    rec.iniciar()
    r = rec.obtener(admin["id"], 1)
    assert r["texto"] == "antiguo" and r["insistir"] is False and r["reintentos"] == 0


def test_hecho_en_repetitivo_normal_no_salta_el_siguiente(admin, monkeypatch):
    monkeypatch.setattr(avisos, "_CANALES", {})
    r = rec.crear(admin["id"], "regar", "todos los días a las 11", ref=REF)
    correr(rec.disparar_vencidos(r["cuando"]))
    manana = datetime(2026, 10, 8, 11, tzinfo=Z).timestamp()
    assert rec.obtener(admin["id"], r["id"])["cuando"] == manana
    assert rec.hecho(admin["id"], r["id"])
    assert rec.obtener(admin["id"], r["id"])["cuando"] == manana


def test_posponer_repetitivo_que_insiste_conserva_su_hora(admin, monkeypatch):
    monkeypatch.setattr(avisos, "_CANALES", {})
    r = rec.crear(admin["id"], "pastilla", "todos los días a las 11", insistir=True, ref=REF)
    correr(rec.disparar_vencidos(r["cuando"]))
    copia = rec.posponer(admin["id"], r["id"], 10)
    assert copia["id"] != r["id"] and copia["insistir"] and not copia["repetir"]
    assert rec.obtener(admin["id"], r["id"])["cuando"] == datetime(2026, 10, 8, 11, tzinfo=Z).timestamp()


def test_marcado_hecho_mientras_se_dispara_no_resucita(admin, monkeypatch):
    enviados = []

    async def emitir(*a, **k):
        enviados.append(a)
        return []
    monkeypatch.setattr(avisos, "emitir", emitir)
    r = rec.crear(admin["id"], "pastilla", "en 10 minutos", insistir=True, ref=REF)
    leidos = rec.vencidos(r["cuando"])
    assert rec.hecho(admin["id"], r["id"])                       # el usuario lo marca justo entre leer y avanzar
    monkeypatch.setattr(rec, "vencidos", lambda ahora: leidos)
    assert correr(rec.disparar_vencidos(r["cuando"])) == []
    assert enviados == [] and rec.obtener(admin["id"], r["id"])["estado"] == "hecho"
