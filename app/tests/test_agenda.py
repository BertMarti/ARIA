"""Agenda y cumpleaños: API y herramientas (CRUD e IDOR), rangos y repeticiones, edades,
resumen de buenos días con agenda y avisos de evento y cumpleaños disparados una sola vez."""
import asyncio
from contextlib import closing
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aria import agenda, auth, avisos, briefing, db, main, recordatorios, rutinas, tiempo, tools, usuarios

LAN = "https://192.168.1.50"
Z = tiempo.zona()


def correr(c):
    return asyncio.run(c)


def d(*a):
    return datetime(*a, tzinfo=Z)


def cliente_de(u) -> TestClient:
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def fechas(eventos):
    return [e["inicio"][:10] for e in eventos]


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


# --- CRUD por API: admin y usuario (los datos son siempre del que habla) ------------------------------------
@pytest.mark.parametrize("rol", ["admin", "usuario"])
def test_api_crud_eventos(admin, ana, rol):
    c = cliente_de(admin if rol == "admin" else ana)
    r = c.post("/api/agenda", json={"titulo": "Dentista", "inicio": "2027-06-01T10:00",
                                    "fin": "2027-06-01T11:00", "lugar": "Clínica", "repeticion": "ninguna"})
    assert r.status_code == 200, r.text
    ev = r.json()["evento"]
    assert ev["titulo"] == "Dentista" and ev["lugar"] == "Clínica" and ev["todo_el_dia"] is False
    assert ev["aviso_min"] is None
    assert ev["inicio"].startswith("2027-06-01T10:00") and ev["fin"].startswith("2027-06-01T11:00")
    eid = ev["id"]
    r = c.patch(f"/api/agenda/{eid}", json={"titulo": "Médico"})
    assert r.status_code == 200 and r.json()["evento"]["titulo"] == "Médico"
    assert c.delete(f"/api/agenda/{eid}").status_code == 200
    # El middleware de permisos rechaza antes de que FastAPI resuelva el método.
    assert c.post(f"/api/agenda/{eid}", json={"titulo": "X"}).status_code in (403, 405)  # método no permitido (al usuario lo para antes permisos.py)


@pytest.mark.parametrize("rol", ["admin", "usuario"])
def test_api_lista_de_eventos(admin, ana, rol):
    c = cliente_de(admin if rol == "admin" else ana)
    r = c.post("/api/agenda", json={"titulo": "Dentista", "inicio": "2027-06-01T10:00", "repeticion": "ninguna"})
    assert r.status_code == 200, r.text
    eid = r.json()["evento"]["id"]
    lista = c.get("/api/agenda", params={"desde": "2027-06-01", "hasta": "2027-07-01"}).json()["eventos"]
    assert [e["id"] for e in lista] == [eid]


@pytest.mark.parametrize("rol", ["admin", "usuario"])
def test_api_crud_cumpleanos(admin, ana, rol):
    c = cliente_de(admin if rol == "admin" else ana)
    r = c.post("/api/cumpleanos", json={"nombre": "Lucía", "dia": 15, "mes": 3, "anio": 1990, "notas": "flores"})
    assert r.status_code == 200, r.text
    cu = r.json()["cumpleanos"]
    assert cu["dia"] == 15 and cu["mes"] == 3 and cu["anio"] == 1990 and cu["notas"] == "flores"
    assert cu["aviso_dias"] == 0
    cid = cu["id"]
    lista = c.get("/api/cumpleanos", params={"dias": 366}).json()["cumpleanos"]
    assert [x["id"] for x in lista] == [cid]
    r = c.patch(f"/api/cumpleanos/{cid}", json={"nombre": "Lucía G."})
    assert r.status_code == 200 and r.json()["cumpleanos"]["nombre"] == "Lucía G."
    assert c.delete(f"/api/cumpleanos/{cid}").status_code == 200
    assert c.get("/api/cumpleanos", params={"dias": 366}).json()["cumpleanos"] == []


def test_api_idor_lectura(admin, ana):
    agenda.crear_evento(admin["id"], {"titulo": "Secreto", "inicio": "2027-06-01T10:00"})
    agenda.crear_cumple(admin["id"], {"nombre": "Secreto", "dia": 1, "mes": 6})
    c = cliente_de(ana)
    assert c.get("/api/agenda", params={"desde": "2027-06-01", "hasta": "2027-07-01"}).json()["eventos"] == []
    assert c.get("/api/cumpleanos", params={"dias": 366}).json()["cumpleanos"] == []
    ev2 = agenda.crear_evento(ana["id"], {"titulo": "De Ana", "inicio": "2027-06-01T12:00"})
    ids = [e["id"] for e in cliente_de(admin).get(
        "/api/agenda", params={"desde": "2027-06-01", "hasta": "2027-07-01"}).json()["eventos"]]
    assert ev2["id"] not in ids


def test_api_idor_escritura(admin, ana):
    ev = agenda.crear_evento(admin["id"], {"titulo": "Secreto", "inicio": "2027-06-01T10:00"})
    cu = agenda.crear_cumple(admin["id"], {"nombre": "Secreto", "dia": 1, "mes": 6})
    c = cliente_de(ana)
    assert c.patch(f"/api/agenda/{ev['id']}", json={"titulo": "mío"}).status_code == 404
    assert c.delete(f"/api/agenda/{ev['id']}").status_code == 404
    assert c.patch(f"/api/cumpleanos/{cu['id']}", json={"nombre": "mío"}).status_code == 404
    assert c.delete(f"/api/cumpleanos/{cu['id']}").status_code == 404
    assert agenda.editar_evento(admin["id"], ev["id"], {})["titulo"] == "Secreto"
    assert agenda.editar_cumple(admin["id"], cu["id"], {})["nombre"] == "Secreto"


# --- Validaciones -------------------------------------------------------------------------------------------
def test_api_validaciones(admin):
    c = cliente_de(admin)
    bogus = [{"titulo": "  ", "inicio": "2027-06-01T10:00"}, {"titulo": "X", "inicio": "el viernes"},
             {"titulo": "X", "inicio": "2027-06-01T10:00", "fin": "2027-06-01T09:00"},
             {"titulo": "X", "inicio": "2027-06-01T10:00", "repeticion": "diaria"},
             {"titulo": "X", "inicio": "2027-06-01T10:00", "aviso_min": 20000},
             {"titulo": "X" * 161, "inicio": "2027-06-01T10:00"}]
    for datos in bogus:
        assert c.post("/api/agenda", json=datos).status_code == 400, datos
    assert c.get("/api/agenda", params={"desde": "2027-06-01", "hasta": "2029-06-01"}).json()["error"]
    for datos in [{"nombre": "", "dia": 1, "mes": 1}, {"nombre": "X", "dia": 30, "mes": 2},
                  {"nombre": "X", "dia": 0, "mes": 5}, {"nombre": "X", "dia": 1, "mes": 13},
                  {"nombre": "X", "dia": 1, "mes": 1, "anio": 9999}]:
        assert c.post("/api/cumpleanos", json=datos).status_code == 400, datos


def test_validaciones_directas(ana):
    uid = ana["id"]
    crear, crear_cumple = agenda.crear_evento, agenda.crear_cumple
    with pytest.raises(agenda.AgendaError, match="título"):
        crear(uid, {"titulo": "  ", "inicio": "2026-10-07T10:00"})
    with pytest.raises(agenda.AgendaError, match="no es válida"):
        crear(uid, {"titulo": "X", "inicio": "el viernes"})
    with pytest.raises(agenda.AgendaError, match="posterior"):
        crear(uid, {"titulo": "X", "inicio": "2026-10-07T10:00", "fin": "2026-10-07T09:00"})
    with pytest.raises(agenda.AgendaError, match="repetición"):
        crear(uid, {"titulo": "X", "inicio": "2026-10-07T10:00", "repeticion": "cada día"})
    with pytest.raises(agenda.AgendaError, match="aviso"):
        crear(uid, {"titulo": "X", "inicio": "2026-10-07T10:00", "aviso_min": "mucho"})
    with pytest.raises(agenda.AgendaError, match="10080"):
        crear(uid, {"titulo": "X", "inicio": "2026-10-07T10:00", "aviso_min": 20000})
    with pytest.raises(agenda.AgendaError, match="rango"):
        agenda.listar_eventos(uid, "2026-10-10", "2026-10-09")
    with pytest.raises(agenda.AgendaError, match="año"):
        agenda.listar_eventos(uid, "2026-01-01", "2030-01-01")
    with pytest.raises(agenda.AgendaError, match="día y mes"):
        crear_cumple(uid, {"nombre": "X", "dia": 30, "mes": 2})
    with pytest.raises(agenda.AgendaError, match="día y mes"):
        crear_cumple(uid, {"nombre": "X", "dia": 0, "mes": 5})
    with pytest.raises(agenda.AgendaError, match="día y mes"):
        crear_cumple(uid, {"nombre": "X", "dia": 1, "mes": 13})
    with pytest.raises(agenda.AgendaError, match="año"):
        crear_cumple(uid, {"nombre": "X", "dia": 1, "mes": 1, "anio": 9999})
    with pytest.raises(agenda.AgendaError, match="año"):
        crear_cumple(uid, {"nombre": "X", "dia": 1, "mes": 1, "anio": 0})


# --- Expansión de repeticiones y límites del rango -----------------------------------------------------------
def test_repeticion_semanal(ana):
    agenda.crear_evento(ana["id"], {"titulo": "Inglés", "inicio": "2026-10-07T10:00", "repeticion": "semanal"})
    assert fechas(agenda.listar_eventos(ana["id"], "2026-10-01", "2026-10-31")) == [
        "2026-10-07", "2026-10-14", "2026-10-21", "2026-10-28"]


def test_repeticion_semanal_con_base_anterior_al_rango(ana):
    agenda.crear_evento(ana["id"], {"titulo": "Inglés", "inicio": "2026-09-30T18:00", "repeticion": "semanal"})
    assert fechas(agenda.listar_eventos(ana["id"], "2026-10-01", "2026-11-01")) == [
        "2026-10-07", "2026-10-14", "2026-10-21", "2026-10-28"]


def test_repeticion_mensual_no_rebota_dias_inexistentes(ana):
    agenda.crear_evento(ana["id"], {"titulo": "Renta", "inicio": "2026-01-31T09:00", "repeticion": "mensual"})
    assert fechas(agenda.listar_eventos(ana["id"], "2026-01-01", "2026-05-01")) == [
        "2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]


def test_repeticion_anual_29_febrero(ana):
    agenda.crear_evento(ana["id"], {"titulo": "Bisiesto", "inicio": "2024-02-29T12:00", "repeticion": "anual"})
    assert fechas(agenda.listar_eventos(ana["id"], "2025-01-01", "2026-01-01")) == ["2025-02-28"]
    assert fechas(agenda.listar_eventos(ana["id"], "2027-01-01", "2028-01-01")) == ["2027-02-28"]
    assert fechas(agenda.listar_eventos(ana["id"], "2028-01-01", "2029-01-01")) == ["2028-02-29"]


def test_repeticion_sin_fin_no_se_extiende_todo_el_ano(ana):
    agenda.crear_evento(ana["id"], {"titulo": "Pago", "inicio": "2026-10-07T10:00", "repeticion": "semanal"})
    evs = agenda.listar_eventos(ana["id"], "2026-10-01", "2026-10-31")
    assert len({e["id"] for e in evs}) == 1
    assert len({e["ocurrencia"] for e in evs}) == 4


def test_repeticion_limita_con_fin(ana):
    agenda.crear_evento(ana["id"], {"titulo": "Curso", "inicio": "2026-10-07T10:00", "fin": "2026-10-07T11:00",
                                    "repeticion": "semanal"})
    evs = agenda.listar_eventos(ana["id"], "2026-10-01", "2026-11-01")
    assert len(evs) == 4
    for e in evs:
        d_i = datetime.fromisoformat(e["inicio"]).replace(second=0, microsecond=0)
        d_f = datetime.fromisoformat(e["fin"]).replace(second=0, microsecond=0)
        assert d_f - d_i == timedelta(hours=1)


def test_rango_semiabierto(ana):
    ev = agenda.crear_evento(ana["id"], {"titulo": "Media", "inicio": "2026-10-31T10:00"})
    assert agenda.listar_eventos(ana["id"], "2026-10-01", "2026-10-31") == []
    assert [e["id"] for e in agenda.listar_eventos(ana["id"], "2026-10-01", "2026-11-01")] == [ev["id"]]


# --- Cumpleaños: edad, 29 de febrero y año desconocido ------------------------------------------------------
def test_edad_y_29_de_febrero(ana):
    c = agenda.crear_cumple(ana["id"], {"nombre": "Bisiesto", "dia": 29, "mes": 2, "anio": 2000})
    r = agenda.listar_cumpleanos(ana["id"], 40, d(2027, 2, 1, 12, 0))
    assert [x["id"] for x in r] == [c["id"]]
    assert r[0]["fecha"] == "2027-02-28" and r[0]["edad"] == 27
    r = agenda.listar_cumpleanos(ana["id"], 40, d(2028, 2, 1, 12, 0))
    assert r[0]["fecha"] == "2028-02-29" and r[0]["edad"] == 28


def test_cumple_sin_anio_y_ya_pasado(ana):
    c1 = agenda.crear_cumple(ana["id"], {"nombre": "Anónima", "dia": 1, "mes": 3})
    c2 = agenda.crear_cumple(ana["id"], {"nombre": "Paca", "dia": 1, "mes": 3, "anio": 2000})
    r = agenda.listar_cumpleanos(ana["id"], 366, d(2026, 10, 1, 12, 0))
    por_nombre = {x["nombre"]: x for x in r}
    assert por_nombre[c1["nombre"]]["fecha"] == "2027-03-01" and por_nombre[c1["nombre"]]["edad"] is None
    assert por_nombre[c2["nombre"]]["fecha"] == "2027-03-01" and por_nombre[c2["nombre"]]["edad"] == 27
    assert agenda.listar_cumpleanos(ana["id"], 0, d(2026, 2, 1, 12, 0)) == []


# --- Herramientas del chat ------------------------------------------------------------------------------------
def test_herramienta_crear_evento_usa_el_uid_del_usuario(admin, ana):
    out = correr(tools.ejecutar("crear_evento", {"titulo": "Gimnasio", "cuando": "mañana a las 8",
                                                 "uid": admin["id"]}, "usuario", uid=ana["id"]))
    assert "Evento creado: «Gimnasio»" in out
    out = correr(tools.ejecutar("crear_evento", {"titulo": "X", "cuando": "nuncajamás"}, "usuario", uid=ana["id"]))
    assert "No entiendo" in out
    out = correr(tools.ejecutar("crear_evento", {"titulo": "S", "cuando": "mañana a las 8"}, "admin", uid=admin["id"]))
    assert "Evento creado: «S»" in out


def test_herramienta_borrar_evento_idor(admin, ana):
    ev = agenda.crear_evento(admin["id"], {"titulo": "Secreto", "inicio": "2026-10-07T18:00"})
    out = correr(tools.ejecutar("borrar_evento", {"id": ev["id"]}, "usuario", uid=ana["id"]))
    assert out == "No encuentro ese evento."
    assert agenda.editar_evento(admin["id"], ev["id"], {})["titulo"] == "Secreto"
    out = correr(tools.ejecutar("borrar_evento", {"id": ev["id"]}, "usuario", uid=admin["id"]))
    assert out == "Evento borrado."
    out = correr(tools.ejecutar("borrar_evento", {"id": ev["id"]}, "usuario", uid=admin["id"]))
    assert out == "No encuentro ese evento."


def test_herramienta_mis_eventos_idor(admin, ana):
    agenda.crear_evento(admin["id"], {"titulo": "Secreto", "inicio": "2026-10-07T18:00"})
    out = correr(tools.ejecutar("mis_eventos", {"desde": "2026-10-01", "hasta": "2026-11-01"}, "usuario", uid=ana["id"]))
    assert "Secreto" not in out


def test_herramienta_cumpleanos(ana):
    out = correr(tools.ejecutar("anadir_cumpleanos", {"nombre": "Luis", "dia": 3, "mes": 12}, "usuario", uid=ana["id"]))
    assert "Cumpleaños añadido: Luis" in out
    out = correr(tools.ejecutar("anadir_cumpleanos", {"nombre": "Luis", "dia": 30, "mes": 2}, "usuario", uid=ana["id"]))
    assert "no existen" in out


def test_herramienta_proximos_cumpleanos_idor(admin, ana):
    agenda.crear_cumple(admin["id"], {"nombre": "Rey", "dia": 15, "mes": 10, "anio": 1980})
    out = correr(tools.ejecutar("proximos_cumpleanos", {"dias": 366}, "usuario", uid=ana["id"]))
    assert "Rey" not in out
    out = correr(tools.ejecutar("proximos_cumpleanos", {"dias": 366}, "usuario", uid=admin["id"]))
    assert "Rey" in out and f"cumple {agenda.listar_cumpleanos(admin['id'], 366)[0]['edad']}" in out


# --- Resumen de buenos días con agenda -----------------------------------------------------------------------
def test_briefing_incluye_eventos_y_cumpleanos(admin, monkeypatch):
    monkeypatch.setattr(briefing, "ultima_copia", lambda: {"disponible": False})
    monkeypatch.setattr(briefing, "_sistema", lambda: None)
    agenda.crear_evento(admin["id"], {"titulo": "Dentista", "inicio": "2026-10-07T18:00"})
    agenda.crear_evento(admin["id"], {"titulo": "Mañana", "inicio": "2026-10-08T10:00"})
    agenda.crear_cumple(admin["id"], {"nombre": "Marta", "dia": 7, "mes": 10, "anio": 1990})
    agenda.crear_cumple(admin["id"], {"nombre": "Lejano", "dia": 27, "mes": 10})
    datos = correr(briefing.construir(admin, d(2026, 10, 7, 10, 0)))
    assert [e["titulo"] for e in datos["agenda"]["eventos"]] == ["Dentista"]
    assert [c["nombre"] for c in datos["agenda"]["cumpleanos"]] == ["Marta"]
    texto = briefing.texto_hablado(datos)
    assert "Dentista" in texto and "Mañana" not in texto
    assert "Marta" in texto and "36" in texto and "Lejano" not in texto


# --- Avisos de agenda (una sola vez) --------------------------------------------------------------------------
def test_aviso_de_evento_una_sola_vez(admin, monkeypatch):
    enviados = []

    async def emitir(*a, **k):
        enviados.append(a)

    monkeypatch.setattr(avisos, "emitir", emitir)
    ev = agenda.crear_evento(admin["id"], {"titulo": "Cita médica", "inicio": "2026-10-07T18:00", "aviso_min": 30})
    monkeypatch.setattr(agenda, "listar_eventos", lambda uid, desde, hasta: [
        agenda._evento({**ev, "ocurrencia": ev["inicio"]})])
    assert correr(agenda.disparar_avisos(d(2026, 10, 7, 17, 0).timestamp())) == []
    assert correr(agenda.disparar_avisos(d(2026, 10, 7, 17, 30).timestamp())) == [ev["id"]]
    assert len(enviados) == 1 and enviados[0][0] == "agenda" and "Cita médica" in enviados[0][2]
    assert correr(agenda.disparar_avisos(d(2026, 10, 7, 17, 45).timestamp())) == []
    assert len(enviados) == 1


def test_aviso_de_evento_recurrente_una_vez_por_ocurrencia(admin, monkeypatch):
    enviados = []

    async def emitir(*a, **k):
        enviados.append(a)

    monkeypatch.setattr(avisos, "emitir", emitir)
    eid = agenda.crear_evento(admin["id"], {"titulo": "Clase", "inicio": "2026-10-07T18:00",
                                            "repeticion": "semanal", "aviso_min": 30})["id"]
    ocurrencias = [d(2026, 10, 7, 18, 0), d(2026, 10, 14, 18, 0)]

    def eventos(uid, desde, hasta):
        return [{"id": eid, "titulo": "Clase", "inicio": f.isoformat(), "fin": None, "todo_el_dia": False,
                 "lugar": "", "notas": "", "repeticion": "semanal", "aviso_min": 30, "creado": 0,
                 "ocurrencia": f.isoformat()} for f in ocurrencias]
    monkeypatch.setattr(agenda, "listar_eventos", eventos)
    assert correr(agenda.disparar_avisos(d(2026, 10, 7, 17, 35).timestamp())) == [eid]
    assert correr(agenda.disparar_avisos(d(2026, 10, 14, 17, 35).timestamp())) == [eid]
    assert len(enviados) == 2
    assert correr(agenda.disparar_avisos(d(2026, 10, 14, 17, 35).timestamp())) == []
    assert len(enviados) == 2


def test_aviso_de_cumpleanos_una_sola_vez(admin, monkeypatch):
    enviados = []

    async def emitir(*a, **k):
        enviados.append(a)

    monkeypatch.setattr(avisos, "emitir", emitir)
    monkeypatch.setattr(agenda, "listar_eventos", lambda uid, desde, hasta: [])
    c = agenda.crear_cumple(admin["id"], {"nombre": "Marta", "dia": 7, "mes": 10, "anio": 1990})
    assert correr(agenda.disparar_avisos(d(2026, 10, 7, 12, 0).timestamp())) == []
    assert correr(agenda.disparar_avisos(d(2026, 10, 7, 9, 5).timestamp())) == [c["id"]]
    assert len(enviados) == 1 and enviados[0][0] == "agenda" and "Marta" in enviados[0][2] and "36" in enviados[0][2]
    assert correr(agenda.disparar_avisos(d(2026, 10, 7, 9, 5).timestamp())) == []
    assert len(enviados) == 1


def test_tick_llama_al_disparo_de_agenda(monkeypatch):
    llamadas = []

    async def disparar(ahora=None):
        llamadas.append(ahora)

    async def nada(*a, **k):
        return []

    monkeypatch.setattr(agenda, "disparar_avisos", disparar)
    monkeypatch.setattr(recordatorios, "disparar_vencidos", nada)
    monkeypatch.setattr(rutinas, "disparar_vencidas", nada)
    monkeypatch.setattr(avisos, "briefings_programados", nada)
    monkeypatch.setattr(avisos, "_CHEQUEOS", {})
    monkeypatch.setattr(avisos, "_ultima_ejecucion", {})
    correr(avisos.tick(1234.0))
    assert llamadas == [1234.0]


# --- Intenciones y permisos -----------------------------------------------------------------------------------
def test_agenda_en_intenciones_y_permisos():
    assert tools.AGENDA <= tools.permitidas("usuario")
    assert tools.AGENDA <= tools.generales()
    assert "crear_evento" in tools.relevantes("apunta una cita en mi agenda el viernes")
    assert "proximos_cumpleanos" in tools.relevantes("¿qué cumpleaños tengo próximamente?")


# --- Casos límite de agenda.py ---
def test_semanal_muy_antiguo_no_rompe_el_listado(ana):
    agenda.crear_evento(ana["id"], {"titulo": "Antigua", "inicio": "2010-01-04T18:00", "repeticion": "semanal"})
    assert len(agenda.listar_eventos(ana["id"], "2026-01-01", "2026-12-31")) == 52


def test_aviso_min_cero_se_conserva(ana):
    ev = agenda.crear_evento(ana["id"], {"titulo": "Reunión", "inicio": "2026-10-07T12:00", "aviso_min": 0})
    assert ev["aviso_min"] == 0


def test_aviso_de_cumpleanos_con_aviso_dias(admin, monkeypatch):
    enviados = []

    async def emitir(*a, **k):
        enviados.append(a)

    monkeypatch.setattr(avisos, "emitir", emitir)
    monkeypatch.setattr(agenda, "listar_eventos", lambda uid, desde, hasta: [])
    c = agenda.crear_cumple(admin["id"], {"nombre": "Marta", "dia": 9, "mes": 10, "aviso_dias": 2})
    assert correr(agenda.disparar_avisos(d(2026, 10, 7, 9, 5).timestamp())) == [c["id"]]
    assert len(enviados) == 1 and "Marta" in enviados[0][2]


def test_herramienta_crear_evento_con_repeticion_deducida(ana):
    out = correr(tools.ejecutar("crear_evento", {"titulo": "Natación", "cuando": "todos los lunes a las 8"},
                                "usuario", uid=ana["id"]))
    assert "Evento creado: «Natación»" in out
    with closing(db._con()) as con:
        fila = con.execute("SELECT repeticion FROM agenda_eventos WHERE titulo=? AND user_id=?",
                           ("Natación", ana["id"])).fetchone()
    assert fila["repeticion"] == "semanal"


def test_ocurrencias_indican_el_inicio_de_la_serie():
    from aria import usuarios
    uid = usuarios.crear("serie@example.invalid", "Serie", "usuario")["id"]
    agenda.crear_evento(uid, {"titulo": "Inglés", "inicio": "2026-10-08T20:00", "repeticion": "semanal"})
    occ = agenda.listar_eventos(uid, "2026-10-15", "2026-10-16")
    assert occ[0]["inicio"].startswith("2026-10-15T20:00") and occ[0]["serie_inicio"].startswith("2026-10-08T20:00")


# --- Exportar a otros calendarios --------------------------------------------------------------------------
def test_ics_con_eventos_repeticiones_avisos_y_cumpleanos(ana):
    agenda.crear_evento(ana["id"], {"titulo": "Inglés; nivel B2, grupo 3", "inicio": "2026-10-08T20:00", "fin": "2026-10-08T21:00",
                                    "repeticion": "semanal", "aviso_min": 30, "lugar": "Online"})
    agenda.crear_evento(ana["id"], {"titulo": "Vacaciones", "inicio": "2026-12-20", "todo_el_dia": True})
    agenda.crear_cumple(ana["id"], {"nombre": "Lucía", "dia": 11, "mes": 10, "anio": 1994})
    t = agenda.ics(ana["id"])
    assert t.startswith("BEGIN:VCALENDAR\r\n") and t.endswith("END:VCALENDAR\r\n")
    assert "SUMMARY:Inglés\; nivel B2\\, grupo 3" in t
    assert "DTSTART:20261008T180000Z" in t and "DTEND:20261008T190000Z" in t   # 20:00 en Madrid (verano) = 18:00 UTC
    assert "RRULE:FREQ=WEEKLY" in t and "TRIGGER:-PT30M" in t and "LOCATION:Online" in t
    assert "DTSTART;VALUE=DATE:20261220" in t and "DTEND;VALUE=DATE:20261221" in t
    assert "SUMMARY:Cumpleaños de Lucía" in t and "DTSTART;VALUE=DATE:19941011" in t
    assert all(len(l.encode()) <= 75 for l in t.split("\r\n"))


def test_suscripcion_con_token_revocable(ana, admin):
    c = cliente_de(ana)
    assert c.get("/api/agenda/suscripcion").json() == {"activa": False}
    agenda.crear_evento(ana["id"], {"titulo": "Dentista", "inicio": "2026-10-09T17:30"})
    ruta = c.post("/api/agenda/suscripcion").json()["ruta"]
    publico = TestClient(main.app, base_url=LAN)   # sin sesión: la app de calendario del móvil
    r = publico.get(ruta)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar") and "Dentista" in r.text
    assert agenda.usuario_de_token(ruta[5:-4]) == ana["id"]
    with closing(db._con()) as con:   # solo se guarda la huella, nunca el token
        assert ruta[5:-4] not in str(con.execute("SELECT * FROM agenda_suscripcion").fetchall()[0][:])
    nueva = c.post("/api/agenda/suscripcion").json()["ruta"]   # regenerar invalida la anterior
    assert publico.get(ruta).status_code == 404 and publico.get(nueva).status_code == 200
    assert c.delete("/api/agenda/suscripcion").json() == {"activa": False}
    assert publico.get(nueva).status_code == 404
    assert publico.get("/cal/corto.ics").status_code == 404
    assert TestClient(main.app, base_url=LAN, follow_redirects=False).post(nueva).status_code in (303, 401, 403, 405)   # solo lectura


def test_descarga_ics_y_rutas_numericas(ana):
    c = cliente_de(ana)
    r = c.get("/api/agenda/ics")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert c.delete("/api/agenda/999999").status_code == 404
