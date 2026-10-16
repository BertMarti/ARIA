"""Exportación y eliminación de cuentas personales."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from aria import auth, db, finanzas, main, mis_datos, notas, usuarios

LAN = "https://192.168.1.50"


def test_exportacion_aisla_datos_y_no_exporta_secretos():
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-ana-larga")
    otro = usuarios.crear("otro@example.com", "Otro", "usuario", "clave-otro-larga")
    cid = db.crear(ana["id"], "Conversación de Ana")
    db.anadir(cid, "user", "mensaje privado")
    otro_cid = db.crear(otro["id"], "Conversación ajena")
    db.anadir(otro_cid, "user", "no debe salir")
    notas.iniciar()
    notas.crear(ana["id"], "Mi nota")
    con = db._con()
    con.execute("INSERT INTO dos_pasos(user_id,secreto,creado) VALUES(?,?,?)", (ana["id"], "secreto-2fa", 1))
    con.commit(); con.close()

    with zipfile.ZipFile(io.BytesIO(mis_datos.exportar(ana["id"], usuarios.por_id(ana["id"], interno=True)))) as z:
        texto = z.read("conversaciones.json").decode()
        assert "mensaje privado" in texto and "no debe salir" not in texto
        assert "pass_hash" not in "".join(z.read(n).decode() for n in z.namelist() if n.endswith(".json"))
        assert "secreto-2fa" not in "".join(z.read(n).decode() for n in z.namelist())
        assert json.loads(z.read("perfil.json"))["email"] == "ana@example.com"


def test_borrado_elimina_datos_personales():
    ana = usuarios.crear("ana2@example.com", "Ana", "usuario")
    cid = db.crear(ana["id"])
    notas.iniciar(); notas.crear(ana["id"], "borrar")
    finanzas.iniciar(); finanzas.registrar(ana["id"], "2026-01-01", "Compra", -100, "Otros")
    mis_datos.borrar(ana["id"])
    assert usuarios.por_id(ana["id"]) is None and db.obtener(cid, ana["id"]) is None
    con = db._con()
    assert con.execute("SELECT COUNT(*) FROM notas WHERE user_id=?", (ana["id"],)).fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM fin_movimientos WHERE user_id=?", (ana["id"],)).fetchone()[0] == 0
    con.close()


def test_borrado_exige_confirmacion_y_protege_al_ultimo_admin():
    ana = usuarios.crear("ana3@example.com", "Ana", "usuario")
    cliente = TestClient(main.app, base_url=LAN, follow_redirects=False)
    cliente.cookies.set(auth.COOKIE, auth.crear_sesion(ana))
    r = cliente.post("/api/mis-datos/borrar-cuenta", json={"confirmacion": "borrar"},
                     headers={"Origin": LAN})
    assert r.status_code == 400 and usuarios.por_id(ana["id"])

    admin = usuarios.por_identificador("admin")
    usuarios.actualizar(ana["id"], rol="admin")
    usuarios.borrar(admin["id"])
    with pytest.raises(usuarios.UsuarioError, match="último administrador"):
        mis_datos.borrar(ana["id"])


def test_no_se_borra_la_cuenta_en_vista_de_prueba():
    jefa = usuarios.crear("jefa@example.com", "Jefa", "admin", "clave-jefa-larga")
    cliente = TestClient(main.app, base_url=LAN, follow_redirects=False)
    cliente.cookies.set(auth.COOKIE, auth.crear_sesion(jefa))
    cliente.cookies.set(main.VISTA_COOKIE, "visita")
    r = cliente.post("/api/mis-datos/borrar-cuenta", json={"confirmacion": "BORRAR"}, headers={"Origin": LAN})
    assert r.status_code == 403 and usuarios.por_id(jefa["id"])
