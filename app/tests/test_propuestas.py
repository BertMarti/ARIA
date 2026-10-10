"""Propuestas (proactividad con permiso): crear, listar, decidir y la API."""
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from aria import agenda, auth, invitados, main, propuestas, recordatorios, tiempo, tools, usuarios

LAN = "https://192.168.1.50"


def cliente(u):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def _usuario(email="ana@example.com", rol="usuario"):
    return usuarios.crear(email, "Ana", rol)


def _futuro(minutos=120):
    return (tiempo.ahora() + timedelta(minutes=minutos)).strftime("%Y-%m-%dT%H:%M")


def _proponer(u, clave="luz:2026-10-10", caduca=None, args=None):
    ahora = time.time()
    return propuestas.crear(u["id"], clave, "luz", "¿Te aviso?", "Detalle", "recordatorio",
                            args or {"texto": "Prueba", "cuando": _futuro()},
                            caduca if caduca is not None else ahora + 3600)


# --- crear() ----------------------------------------------------------------------------------------------------------
def test_crear_y_repetir_la_misma_clave():
    u = _usuario()
    p = _proponer(u)
    assert p["estado"] == "pendiente" and p["herramienta"] == "recordatorio" and p["args"]["cuando"]
    assert _proponer(u) is None                       # misma clave, mismo usuario
    otro = _usuario("pablo@example.com")
    assert _proponer(otro, clave="luz:2026-10-10")    # la misma clave vale para otra persona


def test_herramienta_no_proponible():
    u = _usuario()
    with pytest.raises(propuestas.PropuestaError, match="no se puede proponer"):
        propuestas.crear(u["id"], "luz:x", "luz", "T", "D", "apagar_luz", {}, time.time() + 3600)


def test_caduca_en_el_pasado_y_bandeja_llena(monkeypatch):
    u = _usuario()
    assert _proponer(u, caduca=time.time() - 1) is None
    monkeypatch.setattr(propuestas, "MAX_PENDIENTES", 1)
    assert _proponer(u, clave="luz:a") is not None
    assert _proponer(u, clave="luz:b") is None


# --- listar() y caducar() ----------------------------------------------------------------------------------------------
def _vencer(p):
    """crear() no admite propuestas ya caducadas: se crea vigente y se vence a mano."""
    from contextlib import closing
    from aria import db
    with closing(db._con()) as con, con:
        con.execute("UPDATE propuestas SET caduca=? WHERE id=?", (time.time() - 5, p["id"]))
    return p


def test_listar_solo_las_propias_y_pendientes():
    u1, u2 = _usuario(), _usuario("pablo@example.com")
    p = _proponer(u1)
    _proponer(u2, clave="luz:del-otro")
    vencida = _vencer(_proponer(u1, clave="luz:vencida"))
    assert [x["id"] for x in propuestas.listar(u1["id"])] == [p["id"]]
    assert propuestas.obtener(u1["id"], vencida["id"])["estado"] == "caducada"   # listar caduca las vencidas


def test_caducar_marca_las_vencidas():
    u = _usuario()
    vigente = _proponer(u)
    vencida = _vencer(_proponer(u, clave="luz:vencida"))
    assert propuestas.caducar(ahora=time.time()) == 1
    assert propuestas.obtener(u["id"], vencida["id"])["estado"] == "caducada"
    assert propuestas.obtener(u["id"], vigente["id"])["estado"] == "pendiente"


# --- decidir() ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_decidir_rechazar_y_aprobar_crea_recordatorio():
    u = _usuario()
    p = _proponer(u)
    r = await propuestas.decidir(u, p["id"], False)
    assert r["estado"] == "rechazada" and r["resultado"] is None
    p2 = _proponer(u, clave="luz:aprueba")
    r = await propuestas.decidir(u, p2["id"], True)
    assert r["estado"] == "aprobada" and "Recordatorio" in r["resultado"]
    rs = recordatorios.listar(u["id"])
    assert [x["texto"] for x in rs] == ["Prueba"]
    with pytest.raises(propuestas.PropuestaError, match="aprobada"):
        await propuestas.decidir(u, p2["id"], True)


@pytest.mark.asyncio
async def test_decidir_la_ajena_no_existe():
    u1, u2 = _usuario(), _usuario("pablo@example.com")
    p = _proponer(u1)
    with pytest.raises(propuestas.PropuestaError, match="no existe"):
        await propuestas.decidir(u2, p["id"], True)


@pytest.mark.asyncio
async def test_herramienta_que_falla_deja_la_propuesta_fallida(monkeypatch):
    u = _usuario()
    p = _proponer(u)

    async def falla(*args, **kwargs):
        return "No encuentro ese dispositivo."
    monkeypatch.setattr(tools, "ejecutar", falla)
    r = await propuestas.decidir(u, p["id"], True)
    assert r["estado"] == "fallida" and r["resultado"] == "No encuentro ese dispositivo."


# --- Generadores -------------------------------------------------------------------------------------------------------
def test_citas_propone_media_hora_antes(monkeypatch):
    u = _usuario()
    ahora = tiempo.ahora()
    ini = ahora + timedelta(minutes=90)
    monkeypatch.setattr(agenda, "listar_eventos",
                        lambda uid, desde, hasta: [{"id": 7, "titulo": "Dentista",
                                                    "inicio": ini.isoformat(timespec="minutes"),
                                                    "lugar": "Jaén", "todo_el_dia": False}])
    props = propuestas._citas(u, ahora)
    assert len(props) == 1 and props[0]["herramienta"] == "recordatorio"
    esperado = (ini.replace(second=0, microsecond=0) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
    assert props[0]["args"]["cuando"] == esperado
    assert "Dentista" in props[0]["args"]["texto"] and "Jaén" in props[0]["args"]["texto"]


def test_cita_muy_cercana_no_propone(monkeypatch):
    u = _usuario()
    ahora = tiempo.ahora()
    ini = ahora + timedelta(minutes=10)
    monkeypatch.setattr(agenda, "listar_eventos",
                        lambda uid, desde, hasta: [{"id": 8, "titulo": "Llamada",
                                                    "inicio": ini.isoformat(timespec="minutes"),
                                                    "todo_el_dia": False}])
    assert propuestas._citas(u, ahora) == []


# --- API ---------------------------------------------------------------------------------------------------------------
def test_api_lista_las_propias_pendientes():
    u = _usuario()
    p = _proponer(u)
    _proponer(u, clave="luz:otra", caduca=time.time() - 5)   # caducada: no sale
    r = cliente(u).get("/api/propuestas")
    assert r.status_code == 200
    assert [x["id"] for x in r.json()["propuestas"]] == [p["id"]]


def test_api_rechazar_y_borrar():
    u = _usuario("jefa@example.com", "admin")
    c = cliente(u)
    p = _proponer(u)
    r = c.post(f"/api/propuestas/{p['id']}/rechazar")
    assert r.status_code == 200 and r.json()["propuesta"]["estado"] == "rechazada"
    p2 = _proponer(u, clave="luz:borrar")
    r = c.post(f"/api/propuestas/{p2['id']}/borrar")
    assert r.status_code == 400 and "Decisión" in r.json()["error"]


def test_invitado_no_ve_propuestas():
    s = invitados.solicitar("Ana", "ana@example.com", "Soy la vecina", "1.1.1.1")
    inv = invitados.aprobar(s["id"])["usuario"]
    assert cliente(inv).get("/api/propuestas").status_code == 403


@pytest.mark.asyncio
async def test_dos_aprobaciones_a_la_vez_ejecutan_una_sola_vez(monkeypatch):
    import asyncio
    from aria import tools
    u = _usuario()
    p = _proponer(u)
    llamadas = []

    async def lenta(nombre, args, rol, uid=None, **k):
        llamadas.append(nombre)
        await asyncio.sleep(.05)
        return "Recordatorio 1 programado."
    monkeypatch.setattr(tools, "ejecutar", lenta)
    r = await asyncio.gather(propuestas.decidir(u, p["id"], True), propuestas.decidir(u, p["id"], True), return_exceptions=True)
    assert len(llamadas) == 1 and sum(isinstance(x, propuestas.PropuestaError) for x in r) == 1
    assert propuestas.obtener(u["id"], p["id"])["estado"] == "aprobada"


def test_cita_con_zona_horaria_explicita(monkeypatch):
    from datetime import timedelta, timezone
    from aria import agenda, tiempo
    u = _usuario()
    ahora = tiempo.ahora()
    ini_utc = (ahora + timedelta(minutes=90)).astimezone(timezone.utc)
    monkeypatch.setattr(agenda, "listar_eventos", lambda *a: [{"id": 7, "titulo": "Dentista", "inicio": ini_utc.isoformat()}])
    [c] = propuestas._citas(u, ahora)
    assert c["args"]["cuando"] == (ini_utc.astimezone(ahora.tzinfo) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M")
