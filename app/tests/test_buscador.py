"""Búsqueda global: texto normalizado y aislamiento por usuario."""
from datetime import timedelta

import pytest

from aria import agenda, buscador, db, memoria, notas, recordatorios, tiempo, usuarios


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


def test_encuentra_las_familias_personales(admin):
    uid = admin["id"]
    notas.crear(uid, "Comprar café para Lucía")
    agenda.crear_evento(uid, {"titulo": "Reunión con Lucía", "inicio": (tiempo.ahora() + timedelta(days=2)).isoformat()})
    agenda.crear_cumple(uid, {"nombre": "Lucía", "dia": tiempo.ahora().day, "mes": tiempo.ahora().month})
    recordatorios.crear(uid, "Llamar a Lucía", (tiempo.ahora() + timedelta(hours=2)).isoformat())
    memoria.anadir(uid, "A Lucía le gusta el café")
    cid = db.crear(uid, "Conversación sobre Lucía")
    db.anadir(cid, "user", "Recuerda felicitar a Lucía")

    encontrados = buscador.buscar(uid, "LUCIA")
    assert {r["tipo"] for r in encontrados} == {"nota", "evento", "cumpleanos", "recordatorio", "recuerdo", "conversacion"}
    assert all(len(r["detalle"]) <= 120 for r in encontrados)


def test_no_devuelve_datos_de_otro_usuario_y_limita(admin):
    otro = usuarios.crear("otro@example.com", "Otro", "usuario")
    notas.crear(admin["id"], "secreto compartido")
    notas.crear(otro["id"], "secreto compartido")
    for i in range(12):
        notas.crear(admin["id"], f"elemento secreto {i}")
    assert len([r for r in buscador.buscar(admin["id"], "secreto") if r["tipo"] == "nota"]) == 8
    assert buscador.buscar(otro["id"], "secreto")[0]["id"] != 1
    assert buscador.buscar(admin["id"], "á") == []
    assert buscador.buscar(admin["id"], "x" * 101) == []


def test_invitado_sin_chat_no_ve_conversaciones(admin):
    uid = admin["id"]
    cid = db.crear(uid, "Secreto del chat")
    db.anadir(cid, "user", "Secreto del chat")
    limites = {"secciones": ["inicio"], "memoria": False}
    assert not any(r["tipo"] == "conversacion" for r in buscador.buscar(uid, "secreto", limites))
