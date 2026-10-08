"""Proyectos, decisiones, personalidad y contexto: pruebas aisladas por usuario."""
import json
import pytest

from aria import aprender, memoria, proyectos, tools, usuarios


@pytest.fixture
def admin():
    return usuarios.crear("admin-proyectos@example.invalid", "Admin", "admin", "clave-larga-admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana-proyectos@example.invalid", "Ana", "usuario", "clave-larga-ana")


def test_crud_idor_y_decisiones(admin, ana):
    p = proyectos.crear(ana["id"], "Migración", "Pasar el servicio")
    d = proyectos.registrar_decision(ana["id"], p["id"], "Usar una ventana de mantenimiento", "Reduce el riesgo")
    assert proyectos.listar(admin["id"]) == []
    assert proyectos.decisiones(ana["id"], p["id"])[0]["id"] == d["id"]
    assert not proyectos.borrar(ana["id"], p["id"] + 1000)
    assert proyectos.obtener(admin["id"], p["id"]) is None


def test_personalidad_contexto_y_limite(admin):
    p = proyectos.crear(admin["id"], "Proyecto largo", "x" * 500)
    proyectos.registrar_decision(admin["id"], p["id"], "Una decisión importante")
    memoria.fijar_personalidad(admin["id"], "sincera", True)
    nube = memoria.contexto(admin["id"], "", "Hablemos de Proyecto largo", True)
    local = memoria.contexto(admin["id"], "", "Hablemos de Proyecto largo", False)
    assert "honesta" in nube and "Proyecto largo" in nube and "discrepes" in nube
    assert len(local) <= memoria.PRESUPUESTO_LOCAL


def test_herramientas_e_intenciones(admin):
    assert {"nuevo_proyecto", "registrar_decision", "cambiar_personalidad"} <= tools.relevantes("qué decidimos sobre mi proyecto") | tools.PROYECTOS
    assert "mis_proyectos" in tools.permitidas("usuario")


def test_decisiones_aprendidas_solo_si_existe(admin):
    p = proyectos.crear(admin["id"], "Web nueva")
    respuesta = json.dumps({"hechos": [], "decisiones": [
        {"proyecto": "Web nueva", "decision": "Al final vamos a usar HTML", "motivo": "Sencillez"},
        {"proyecto": "Inventado", "decision": "No guardar"},
    ]})
    assert len(aprender.parsear_decisiones(respuesta, proyectos.listar(admin["id"]))) == 1
    assert aprender.parsear_decisiones(respuesta, []) == []
