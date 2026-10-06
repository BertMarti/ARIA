import pytest

from aria import config, db


@pytest.fixture(autouse=True)
def bd(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    db.iniciar()


def test_titulo_desde_primeras_palabras():
    assert db.titulo_desde("  Hola   mundo ") == "Hola mundo"
    t = db.titulo_desde("palabra " * 30)
    assert len(t) <= db.MAX_TITULO + 1 and t.endswith("…")


def test_ciclo_de_vida():
    cid = db.crear()
    assert db.es_primer_mensaje(cid)
    db.anadir(cid, "user", "hola")
    db.anadir(cid, "tool", db.herramienta_json("estado_sistema", {}))
    db.anadir(cid, "assistant", "qué tal")
    assert [m["role"] for m in db.obtener(cid)["mensajes"]] == ["user", "tool", "assistant"]
    assert [m["role"] for m in db.historial_modelo(cid, 40)] == ["user", "assistant"]
    assert db.renombrar(cid, "Nuevo título") and db.obtener(cid)["titulo"] == "Nuevo título"
    assert not db.renombrar(cid, "   ")
    assert db.borrar(cid) and db.obtener(cid) is None and not db.borrar(cid)


def test_orden_reciente_primero_y_limite_de_contexto():
    a, b = db.crear("a"), db.crear("b")
    db.anadir(a, "user", "x")
    assert db.listar()[0]["id"] == a
    for i in range(10):
        db.anadir(b, "user", str(i))
    assert [m["content"] for m in db.historial_modelo(b, 3)] == ["7", "8", "9"]
