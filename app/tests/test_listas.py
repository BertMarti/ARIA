from aria import invitados, listas, mis_datos, usuarios


def _preparar():
    listas.iniciar()
    return usuarios.por_identificador("admin")


def test_compra_separa_y_no_duplica():
    admin = _preparar()
    compra = next(x for x in listas.listar(admin["id"]) if x["nombre"] == "La compra")
    listas.anadir_items(admin["id"], compra["id"], "leche, pan y huevos")
    listas.anadir_items(admin["id"], compra["id"], "Leche")
    assert [x["texto"] for x in listas.obtener(admin["id"], compra["id"])["items"]] == ["leche", "pan", "huevos"]


def test_casa_compartida_y_privada():
    admin = _preparar()
    otra = usuarios.crear("lista@example.com", "Lista", "usuario", "clave-larga-lista")
    casa = listas.crear(admin["id"], "Casa", "🏠", "todos")
    privada = listas.crear(admin["id"], "Privada")
    assert listas.obtener(otra["id"], casa["id"])
    assert listas.obtener(otra["id"], privada["id"]) is None
    listas.anadir_items(otra["id"], casa["id"], "sal")
    assert listas.obtener(admin["id"], casa["id"])["pendientes"] == 1


def test_borrar_y_exportar_solo_datos_propios():
    admin = _preparar()
    otra = usuarios.crear("exporta@example.com", "Exporta", "usuario", "clave-larga-exporta")
    propia = listas.crear(otra["id"], "Propia")
    listas.anadir_items(otra["id"], propia["id"], "café")
    assert not listas.borrar(admin["id"], propia["id"])
    assert b"listas.json" in mis_datos.exportar(otra["id"], otra)
    assert invitados.de(otra["id"]) is None
