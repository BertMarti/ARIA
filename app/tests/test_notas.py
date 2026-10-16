import json

from aria import config, notas, tools, usuarios


def test_crud_y_aislamiento():
    admin = usuarios.por_identificador("admin")
    otra = usuarios.crear("notas@example.com", "Notas", "usuario", "clave-larga-notas")
    n = notas.crear(admin["id"], "Cambiar la luz", "mejora")
    assert notas.listar(admin["id"])[0]["texto"] == "Cambiar la luz"
    assert notas.editar(admin["id"], n["id"], texto="Cambiar la luz del salón", estado="hecha")["estado"] == "hecha"
    assert notas.editar(otra["id"], n["id"], texto="intrusión") is None
    assert not notas.borrar(otra["id"], n["id"])
    assert notas.borrar(admin["id"], n["id"])


def test_crear_varias_y_exportar_mejoras():
    admin = usuarios.por_identificador("admin")
    usuario = usuarios.crear("persona@example.com", "Persona", "usuario", "clave-larga-persona")
    creadas = notas.crear_varias(admin["id"], "- Una\n* Dos\n• Tres", "mejora", "telegram")
    notas.crear(usuario["id"], "No exportar", "mejora")
    notas.crear(admin["id"], "Ya hecha", "mejora")
    ya_hecha = next(x for x in notas.listar(admin["id"]) if x["texto"] == "Ya hecha")
    notas.editar(admin["id"], ya_hecha["id"], estado="hecha")
    datos = json.loads((config.DATA_DIR / "host" / "notas-mejoras.json").read_text())
    assert [x["id"] for x in datos] == [x["id"] for x in creadas]
    assert all(x["origen"] == "telegram" for x in datos)


def test_herramientas_notas():
    import asyncio
    admin = usuarios.por_identificador("admin")
    resultado = asyncio.run(tools.ejecutar("apuntar_nota", {"texto": "Comprar pilas", "categoria": "compra"}, "admin", admin["id"]))
    assert "Nota apuntada" in resultado
    listado = asyncio.run(tools.ejecutar("mis_notas", {"estado": "abierta"}, "usuario", admin["id"]))
    assert "Comprar pilas" in listado
