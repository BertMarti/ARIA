"""Recordatorios: interpretar fechas en español, repeticiones, CRUD por usuario, herramientas y disparo."""
import asyncio
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from aria import auth, avisos, main, recordatorios as rec, tiempo, tools, usuarios

LAN = "https://192.168.1.50"
Z = tiempo.zona()
# Miércoles 7 de octubre de 2026, 10:00 (hora de Madrid)
REF = datetime(2026, 10, 7, 10, 0, tzinfo=Z)


def correr(c):
    return asyncio.run(c)


def d(*a):
    return datetime(*a, tzinfo=Z)


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


@pytest.mark.parametrize("frase,esperado,repetir", [
    ("2026-10-09T09:00", d(2026, 10, 9, 9, 0), None),
    ("2026-10-09 18:30", d(2026, 10, 9, 18, 30), None),
    ("2026-10-09", d(2026, 10, 9, 9, 0), None),
    ("en 20 minutos", d(2026, 10, 7, 10, 20), None),
    ("dentro de 2 horas", d(2026, 10, 7, 12, 0), None),
    ("en media hora", d(2026, 10, 7, 10, 30), None),
    ("en una hora", d(2026, 10, 7, 11, 0), None),
    ("mañana a las 9", d(2026, 10, 8, 9, 0), None),
    ("mañana a las 9 de la noche", d(2026, 10, 8, 21, 0), None),
    ("mañana por la mañana", d(2026, 10, 8, 9, 0), None),
    ("pasado mañana a las 10:30", d(2026, 10, 9, 10, 30), None),
    ("hoy a las 18:00", d(2026, 10, 7, 18, 0), None),
    ("hoy a las 5", d(2026, 10, 7, 17, 0), None),  # las 5 de la mañana ya pasaron: las 17
    ("a las 9", d(2026, 10, 7, 21, 0), None),
    ("esta tarde", d(2026, 10, 7, 17, 0), None),
    ("esta noche", d(2026, 10, 7, 21, 0), None),
    ("el viernes por la tarde", d(2026, 10, 9, 17, 0), None),
    ("el viernes a las 8 y media", d(2026, 10, 9, 8, 30), None),
    ("el miércoles a las 9", d(2026, 10, 14, 9, 0), None),  # hoy es miércoles y las 9 ya pasaron
    ("el lunes", d(2026, 10, 12, 9, 0), None),
    ("el 15 de octubre a las 10", d(2026, 10, 15, 10, 0), None),
    ("el 3 de enero", d(2027, 1, 3, 9, 0), None),
    ("todos los lunes a las 8", d(2026, 10, 12, 8, 0), "semanal"),
    ("todos los días a las 7:30", d(2026, 10, 8, 7, 30), "diario"),
    ("cada día a las 22:00", d(2026, 10, 7, 22, 0), "diario"),
    ("de lunes a viernes a las 7", d(2026, 10, 8, 7, 0), "laborables"),
    ("a mediodía", d(2026, 10, 7, 13, 0), None),
])
def test_interpretar(frase, esperado, repetir):
    assert rec.interpretar(frase, REF) == (esperado, repetir)


@pytest.mark.parametrize("frase", ["", "cuando puedas", "algún día", "el 31 de febrero"])
def test_interpretar_no_entiende(frase):
    with pytest.raises(rec.RecordatorioError):
        rec.interpretar(frase, REF)


def test_laborables_salta_el_fin_de_semana():
    viernes_noche = datetime(2026, 10, 9, 20, 0, tzinfo=Z)
    assert rec.interpretar("de lunes a viernes a las 7", viernes_noche) == (d(2026, 10, 12, 7, 0), "laborables")


def test_siguiente_repeticion_y_cambio_de_hora():
    # El 25/10/2026 acaba el horario de verano: el recordatorio sigue a las 08:00 locales.
    s = rec.siguiente(d(2026, 10, 19, 8, 0), "semanal", d(2026, 10, 19, 8, 1))
    assert s == d(2026, 10, 26, 8, 0) and s.utcoffset().total_seconds() == 3600
    assert rec.siguiente(d(2026, 10, 24, 8, 0), "diario", d(2026, 10, 24, 9, 0)) == d(2026, 10, 25, 8, 0)
    assert rec.siguiente(d(2026, 10, 9, 7, 0), "laborables", d(2026, 10, 9, 7, 1)) == d(2026, 10, 12, 7, 0)
    # si ARIA estuvo apagada varios días, salta las repeticiones perdidas
    assert rec.siguiente(d(2026, 10, 1, 8, 0), "diario", d(2026, 10, 7, 10, 0)) == d(2026, 10, 8, 8, 0)


def test_crear_listar_borrar_por_usuario(admin, ana):
    r = rec.crear(ana["id"], "que llame al taller", "mañana a las 9", ref=REF)
    assert r["texto"] == "llame al taller" and r["descripcion"] == "mañana a las 09:00"
    assert [x["id"] for x in rec.listar(ana["id"], REF)] == [r["id"]] and rec.listar(admin["id"]) == []
    assert not rec.borrar(admin["id"], r["id"]) and rec.listar(ana["id"])
    assert rec.borrar(ana["id"], r["id"]) and rec.listar(ana["id"]) == []


def test_crear_valida(ana):
    with pytest.raises(rec.RecordatorioError, match="ya ha pasado"):
        rec.crear(ana["id"], "x", "2026-10-07T09:00", ref=REF)
    with pytest.raises(rec.RecordatorioError, match="repetición"):
        rec.crear(ana["id"], "x", "mañana", "mensual", ref=REF)
    with pytest.raises(rec.RecordatorioError, match="Qué"):
        rec.crear(ana["id"], "  ", "mañana", ref=REF)
    r = rec.crear(ana["id"], "regar", "2026-10-07T09:00", "diario", ref=REF)  # recurrente en el pasado: la próxima
    assert r["cuando"] == d(2026, 10, 8, 9, 0).timestamp() and r["descripcion"] == "todos los días a las 09:00"


def test_herramientas_de_recordatorio(admin, ana):
    assert tools.RECORDATORIOS <= tools.permitidas("usuario")
    out = correr(tools.ejecutar("recordatorio", {"texto": "sacar la basura", "cuando": "en 20 minutos"}, "usuario", uid=ana["id"]))
    assert out.startswith("Recordatorio") and "sacar la basura" in out
    out = correr(tools.ejecutar("recordatorio", {"texto": "x", "cuando": "cuando sea"}, "usuario", uid=ana["id"]))
    assert "No entiendo" in out
    # el uid nunca sale de los argumentos del modelo
    correr(tools.ejecutar("recordatorio", {"texto": "trampa", "cuando": "en 5 minutos", "uid": admin["id"]}, "usuario", uid=ana["id"]))
    assert rec.listar(admin["id"]) == []
    assert "sacar la basura" in correr(tools.ejecutar("mis_recordatorios", {}, "usuario", uid=ana["id"]))
    assert "No tienes" in correr(tools.ejecutar("mis_recordatorios", {}, "admin", uid=admin["id"]))
    assert "borrado" in correr(tools.ejecutar("borrar_recordatorio", {"id_o_texto": "basura"}, "usuario", uid=ana["id"]))
    assert "No encuentro" in correr(tools.ejecutar("borrar_recordatorio", {"id_o_texto": "basura"}, "usuario", uid=ana["id"]))


@pytest.mark.parametrize("texto,esperadas,no", [
    ("Recuérdame mañana a las 9 llamar al taller", {"recordatorio"}, {"recordar"}),
    ("avísame en 20 minutos de sacar la pizza", {"recordatorio"}, set()),
    ("ponme un recordatorio para el viernes", {"recordatorio"}, set()),
    ("¿qué recordatorios tengo?", {"mis_recordatorios"}, {"recordatorio"}),
    ("borra el recordatorio 3", {"borrar_recordatorio"}, set()),
    ("Recuerda que mi equipo es el Betis", {"recordar"}, {"recordatorio"}),
    ("Apunta que cenamos a las 9", {"recordar"}, {"recordatorio"}),
])
def test_intenciones_para_el_modelo_local(texto, esperadas, no):
    r = tools.relevantes(texto)
    assert esperadas <= r and not (r & no), r


def test_disparo_posponer_y_hecho(admin, monkeypatch):
    llegados = []

    async def canal(uid, aviso):
        llegados.append(aviso)
        return True
    monkeypatch.setattr(avisos, "_CANALES", {"falso": canal})
    monkeypatch.setattr(avisos, "en_silencio", lambda a, ref=None: True)  # los recordatorios ignoran el silencio
    r = rec.crear(admin["id"], "tomar la pastilla", "en 10 minutos", ref=REF)
    assert correr(rec.disparar_vencidos(REF.timestamp())) == []
    assert correr(rec.disparar_vencidos(REF.timestamp() + 601)) == [r["id"]]
    assert llegados[0]["texto"] == "Recordatorio: tomar la pastilla" and llegados[0]["recordatorio"] == r["id"]
    assert correr(rec.disparar_vencidos(REF.timestamp() + 700)) == []  # no se repite
    assert rec.listar(admin["id"]) == []
    p = rec.posponer(admin["id"], r["id"], 10)
    assert p["estado"] == "pendiente" and rec.listar(admin["id"])
    assert rec.hecho(admin["id"], r["id"]) and rec.obtener(admin["id"], r["id"])["estado"] == "hecho"
    assert rec.posponer(999, r["id"], 10) is None


def test_recurrente_se_reprograma(admin, monkeypatch):
    monkeypatch.setattr(avisos, "_CANALES", {})
    r = rec.crear(admin["id"], "regar", "todos los días a las 11", ref=REF)
    assert r["cuando"] == d(2026, 10, 7, 11, 0).timestamp()
    correr(rec.disparar_vencidos(d(2026, 10, 7, 11, 0).timestamp()))
    assert rec.obtener(admin["id"], r["id"])["cuando"] == d(2026, 10, 8, 11, 0).timestamp()
    # posponer un recurrente crea uno puntual y deja la serie intacta
    p = rec.posponer(admin["id"], r["id"], 60)
    assert p["id"] != r["id"] and p["repetir"] is None and len(rec.listar(admin["id"])) == 2


def test_api_recordatorios_e_idor(admin, ana):
    def cli(u):
        c = TestClient(main.app, base_url=LAN, follow_redirects=False)
        c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
        return c
    ca = cli(ana)
    r = ca.post("/api/recordatorios", json={"texto": "dentista", "cuando": "2027-06-01T10:00"})
    assert r.status_code == 200
    rid = r.json()["recordatorio"]["id"]
    assert ca.post("/api/recordatorios", json={"texto": "x", "cuando": "nunca jamás"}).status_code == 400
    assert cli(admin).get("/api/recordatorios").json()["recordatorios"] == []
    assert cli(admin).delete(f"/api/recordatorios/{rid}").status_code == 404
    assert ca.delete(f"/api/recordatorios/{rid}").status_code == 200
