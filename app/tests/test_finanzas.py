"""Finanzas: CSV de bancos españoles, deduplicado, presupuestos y aislamiento entre usuarios (IDOR)."""
import base64

import pytest

from aria import finanzas, finanzas_csv as fcsv, usuarios
from tests.test_permisos import cliente_de

# 1) Estilo CaixaBank/Santander: preámbulo, «;», coma decimal, columna Importe, latin-1.
CSV_IMPORTE = ("Titular;ANA PÉREZ\nCuenta;ES00 0000 0000 0000\n\n"
               "Fecha;Fecha valor;Concepto;Importe;Saldo\n"
               "03/10/2026;03/10/2026;COMPRA TARJ. 1234 MERCADONA VALENCIA;-45,30;1.954,70\n"
               "01/10/2026;01/10/2026;NÓMINA OCTUBRE EMPRESA SL;2.000,00;2.000,00\n"
               "05/10/2026;05/10/2026;RECIBO NETFLIX.COM;-12,99;1.941,71\n"
               "05/10/2026;05/10/2026;RECIBO NETFLIX.COM;-12,99;1.928,72\n").encode("latin-1")
# 2) Estilo BBVA/ING: «,» como separador, columnas Debe/Haber, punto decimal, UTF-8 con BOM, fecha dd/mm/aa.
CSV_DEBE_HABER = ("﻿F. Operación,Descripción,Debe,Haber\n"
                  "02/09/26,Repsol estación 33,\"60.00\",\n"
                  "15/09/26,Transferencia recibida,,\"150.50\"\n"
                  "20/09/26,Farmacia López,\"8.75\",\n").encode("utf-8")
# 3) Estilo exportación genérica: tabuladores, fecha ISO, importes con € y miles.
CSV_TAB = ("fecha\tconcepto\tcantidad\tcuenta\n"
           "2026-08-01\tAlquiler piso\t-1.100,00 €\tES11\n"
           "2026-08-02\tBizum de Juan\t25,00 €\tES11\n"
           "fila rota\t\t\t\n").encode("utf-8")


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def _conv(datos):
    info = fcsv.leer(datos)
    return info, fcsv.convertir(info["filas"], info["mapeo"], len(info["cabecera"]))


def test_csv_importe_latin1_preambulo():
    info, c = _conv(CSV_IMPORTE)
    assert info["separador"] == ";" and info["codificacion"] in ("cp1252", "latin-1")
    assert info["mapeo"]["fecha"] == 0 and info["mapeo"]["concepto"] == 2 and info["mapeo"]["importe"] == 3
    m = c["movimientos"]
    assert m[0] == {"fecha": "2026-10-03", "concepto": "COMPRA TARJ. 1234 MERCADONA VALENCIA", "importe": -4530, "cuenta": None}
    assert m[1]["importe"] == 200000 and m[1]["concepto"].startswith("NÓMINA")
    assert c["errores"] == []


def test_csv_debe_haber_utf8_coma():
    info, c = _conv(CSV_DEBE_HABER)
    assert info["separador"] == "," and info["mapeo"]["debe"] == 2 and info["mapeo"]["haber"] == 3
    assert [x["importe"] for x in c["movimientos"]] == [-6000, 15050, -875]
    assert c["movimientos"][0]["fecha"] == "2026-09-02" and c["movimientos"][2]["concepto"] == "Farmacia López"


def test_csv_tabulador_iso_euros():
    info, c = _conv(CSV_TAB)
    assert info["separador"] == "\t" and info["mapeo"]["cuenta"] == 3
    assert [x["importe"] for x in c["movimientos"]] == [-110000, 2500]
    assert c["errores"] == [3]


@pytest.mark.parametrize("texto,dec,esperado", [
    ("1.234,56", ",", 123456), ("-12,3", ",", -1230), ("(5,00)", ",", -500), ("12,30-", ",", -1230),
    ("1,234.56", ",", 123456), ("7.5", ".", 750), ("+3", ",", 300), ("abc", ",", None), ("1,2,3", ",", None),
])
def test_parse_importe(texto, dec, esperado):
    assert fcsv.parse_importe(texto, dec) == esperado


def test_csv_sin_cabecera_y_binario():
    with pytest.raises(fcsv.CsvError):
        fcsv.leer(b"a;b;c\n1;2;3\n")
    with pytest.raises(fcsv.CsvError):
        fcsv.leer(b"\x00\x01\x02binario")
    with pytest.raises(fcsv.CsvError):
        fcsv.validar_mapeo({"fecha": 0, "concepto": 9}, 3)


def test_importar_deduplica_y_categoriza(admin):
    _, c = _conv(CSV_IMPORTE)
    r = finanzas.importar(admin["id"], c["movimientos"])
    assert r == {"insertados": 4, "duplicados": 0}  # los dos Netflix iguales se conservan
    r = finanzas.importar(admin["id"], c["movimientos"])
    assert r == {"insertados": 0, "duplicados": 4}
    movs = {m["concepto"]: m for m in finanzas.listar(admin["id"])}
    assert movs["COMPRA TARJ. 1234 MERCADONA VALENCIA"]["categoria"] == "Supermercado"
    assert movs["RECIBO NETFLIX.COM"]["categoria"] == "Suscripciones"
    assert movs["NÓMINA OCTUBRE EMPRESA SL"]["categoria"] == "Ingresos"
    assert all(m["origen"] == "csv" for m in movs.values())


def test_resumen_presupuestos_y_comparar(admin):
    uid = admin["id"]
    finanzas.registrar(uid, "2026-10-02", "Mercadona", -100)
    finanzas.registrar(uid, "2026-10-03", "Cena", "-30,50", "Restaurantes")
    finanzas.registrar(uid, "2026-10-01", "Nómina", 1500)
    finanzas.registrar(uid, "2026-09-05", "Mercadona", -80)
    r = finanzas.resumen_mes(uid, "2026-10")
    assert (r["ingresos"], r["gastos"], r["balance"]) == (150000, 13050, 136950)
    assert r["categorias"][0] == {"categoria": "Supermercado", "total": 10000, "movimientos": 1}
    finanzas.fijar_presupuesto(uid, "Supermercado", 90)
    finanzas.fijar_presupuesto(uid, "Restaurantes", "50")
    e = {x["categoria"]: x for x in finanzas.estado_presupuestos(uid, "2026-10")}
    assert e["Supermercado"]["superado"] and e["Supermercado"]["restante"] == -1000
    assert not e["Restaurantes"]["superado"] and e["Restaurantes"]["porcentaje"] == 61.0
    finanzas.fijar_presupuesto(uid, "Restaurantes", 0)
    assert {x["categoria"] for x in finanzas.estado_presupuestos(uid, "2026-10")} == {"Supermercado"}
    c = finanzas.comparar_meses(uid, "2026-09", "2026-10")
    assert c["a"]["gastos"] == 8000 and c["b"]["gastos"] == 13050
    with pytest.raises(finanzas.FinanzasError):
        finanzas.mes_valido("octubre")
    with pytest.raises(finanzas.FinanzasError):
        finanzas.registrar(uid, "hoy", "x", 0)


def test_regla_de_usuario_al_editar(admin):
    uid = admin["id"]
    m = finanzas.registrar(uid, "2026-10-02", "COMPRA TARJ. 9999 FRUTERIA PACO", -12)
    assert m["categoria"] is None
    finanzas.actualizar(uid, m["id"], {"categoria": "Supermercado", "aplicar_a_similares": True})
    m2 = finanzas.registrar(uid, "2026-10-09", "COMPRA TARJ. 1111 FRUTERIA PACO", -8)
    assert m2["categoria"] == "Supermercado"


def test_idor_entre_usuarios(admin, ana):
    m = finanzas.registrar(admin["id"], "2026-10-02", "Secreto del admin", -500)
    c = cliente_de(ana)
    assert c.get("/api/finanzas/movimientos").json()["movimientos"] == []
    assert c.patch(f"/api/finanzas/movimientos/{m['id']}", json={"importe": 1}).status_code == 404
    assert c.delete(f"/api/finanzas/movimientos/{m['id']}").status_code == 404
    assert c.get("/api/finanzas/resumen?mes=2026-10").json()["gastos"] == 0
    assert finanzas.obtener(admin["id"], m["id"])["importe"] == -50000
    # lo de Ana tampoco lo ve el admin
    r = c.post("/api/finanzas/movimientos", json={"fecha": "2026-10-02", "concepto": "Café", "importe": -2})
    mid = r.json()["movimiento"]["id"]
    assert cliente_de(admin).delete(f"/api/finanzas/movimientos/{mid}").status_code == 404
    assert all(x["concepto"] != "Café" for x in cliente_de(admin).get("/api/finanzas/movimientos").json()["movimientos"])
    # borrar al usuario borra sus finanzas
    cliente_de(admin).delete(f"/api/users/{ana['id']}")
    assert finanzas.listar(ana["id"]) == []


def test_importacion_por_api(ana):
    c = cliente_de(ana)
    b64 = base64.b64encode(CSV_DEBE_HABER).decode()
    p = c.post("/api/finanzas/importar/previa", json={"archivo": b64}).json()
    assert p["validas"] == 3 and p["cabecera"][2] == "Debe" and len(p["muestra"]) == 3
    r = c.post("/api/finanzas/importar", json={"archivo": b64, "mapeo": p["mapeo"], "cuenta": "BBVA"}).json()
    assert r["insertados"] == 3
    assert c.post("/api/finanzas/importar", json={"archivo": b64, "mapeo": p["mapeo"]}).json()["duplicados"] == 3
    assert c.post("/api/finanzas/importar", json={"archivo": "no-es-base64!"}).status_code == 400
    assert c.post("/api/finanzas/importar", json={"archivo": b64, "mapeo": {"fecha": 99}}).status_code == 400
