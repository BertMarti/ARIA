"""Progreso de medios: validación, límite, aislamiento, permisos y exportación."""
import io
import json
import zipfile

from aria import auth, db, medios, mis_datos, usuarios
from tests.test_permisos import cliente_de

import pytest


@pytest.fixture
def ana():
    medios.iniciar()
    return usuarios.crear("ana-medios@example.com", "Ana", "usuario", "clave-ana-larga")


def test_progreso_valida_huella_numeros_y_nombre(ana):
    medios.iniciar()
    c = cliente_de(ana)
    assert c.post("/api/medios/progreso", json={"huella": "x", "nombre": "a", "posicion": 1, "duracion": 2}).status_code == 400
    assert c.post("/api/medios/progreso", json={"huella": "a" * 64, "nombre": "a", "posicion": "NaN", "duracion": 2}).status_code == 400
    assert c.post("/api/medios/progreso", json={"huella": "a" * 64, "nombre": "x" * 201, "posicion": 1, "duracion": 2}).status_code == 400


def test_progreso_limita_filas_y_aisla_usuarios(ana):
    medios.iniciar()
    admin = usuarios.por_identificador("admin")
    for i in range(3001):
        medios.guardar(ana["id"], f"{i:064x}", f"vídeo {i}", 1, 10)
    con = db._con()
    assert con.execute("SELECT COUNT(*) FROM medios_progreso WHERE user_id=?", (ana["id"],)).fetchone()[0] == 3000
    con.close()
    assert cliente_de(admin).get("/api/medios/progreso", params={"h": f"{0:064x}"}).json()["progreso"] == []


def test_invitado_no_tiene_progreso():
    assert not __import__("aria.permisos", fromlist=["permitido"]).permitido("familiar", "GET", "/api/medios/progreso")


def test_exportacion_incluye_medios(ana):
    medios.iniciar()
    medios.guardar(ana["id"], "b" * 64, "película.mp4", 12, 100)
    with zipfile.ZipFile(io.BytesIO(mis_datos.exportar(ana["id"], usuarios.por_id(ana["id"], interno=True)))) as z:
        datos = json.loads(z.read("medios.json"))
    assert datos[0]["nombre"] == "película.mp4"
