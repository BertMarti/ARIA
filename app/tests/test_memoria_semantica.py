"""Memoria semántica local, confianza y olvido automático."""
import asyncio
import time
from array import array

import pytest

from aria import config, db, embeddings, memoria, usuarios


@pytest.fixture
def admin():
    return usuarios.crear("jefa@example.com", "Jefa", "admin")


def correr(coro):
    return asyncio.run(coro)


def poner_vector(rid, vector):
    with db._con() as con:
        con.execute("INSERT INTO memoria_vectores (recuerdo_id, modelo, vector) VALUES (?,?,?)",
                    (rid, config.EMBEDDINGS, array("f", vector).tobytes()))


def test_orden_semantico_y_caida_al_lexico(admin, monkeypatch):
    monkeypatch.setattr(config, "EMBEDDINGS", "modelo-prueba")
    a, _ = memoria.anadir(admin["id"], "Le gustan los senderos de montaña", "usuario")
    b, _ = memoria.anadir(admin["id"], "Su mascota es un loro verde", "usuario")
    poner_vector(a["id"], [1, 0]); poner_vector(b["id"], [0, 1])
    monkeypatch.setattr(embeddings, "vectores", lambda textos, **k: asyncio.sleep(0, result=[[0, 1]]))
    assert correr(memoria.relevantes(admin["id"], "animal doméstico", 2)) == [b["id"], a["id"]]
    monkeypatch.setattr(embeddings, "vectores", lambda textos, **k: asyncio.sleep(0, result=None))
    assert correr(memoria.relevantes(admin["id"], "otro asunto distinto", 2)) is None


def test_confianza_sube_al_usarse_y_purga_solo_automaticos(admin):
    auto, _ = memoria.anadir(admin["id"], "Aprendido sobre una afición inventada", "auto")
    usuario, _ = memoria.anadir(admin["id"], "El usuario eligió un color inventado", "usuario")
    antes = memoria.obtener(admin["id"], auto["id"])["confianza"]
    memoria.contexto(admin["id"], "A", "hola", True)
    assert memoria.obtener(admin["id"], auto["id"])["confianza"] > antes
    viejo = time.time() - 91 * 86400
    with db._con() as con:
        con.execute("UPDATE recuerdos SET creado=?, usado=NULL WHERE id IN (?,?)", (viejo, auto["id"], usuario["id"]))
        con.execute("UPDATE recuerdos SET confianza=.6 WHERE id=?", (auto["id"],))
    assert memoria.purgar_automaticos(time.time()) == 1
    assert memoria.obtener(admin["id"], auto["id"]) is None
    assert memoria.obtener(admin["id"], usuario["id"]) is not None


def test_vector_se_borra_en_cascada(admin):
    rec, _ = memoria.anadir(admin["id"], "Dato inventado para cascada", "usuario")
    poner_vector(rec["id"], [1, 0])
    assert memoria.borrar(admin["id"], rec["id"])
    with db._con() as con:
        assert con.execute("SELECT 1 FROM memoria_vectores WHERE recuerdo_id=?", (rec["id"],)).fetchone() is None


def test_espera_tras_fallo(monkeypatch):
    monkeypatch.setattr(config, "EMBEDDINGS", "modelo-prueba")
    embeddings._fallo_hasta = 0
    llamadas = []

    class Cliente:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            llamadas.append(1)
            raise RuntimeError("fallo")

    monkeypatch.setattr(embeddings.httpx, "AsyncClient", lambda **kwargs: Cliente())
    assert correr(embeddings.vectores(["texto inventado"])) is None
    assert correr(embeddings.vectores(["texto inventado"])) is None
    assert len(llamadas) == 1


def test_la_lentitud_del_chat_no_castiga(monkeypatch):
    import httpx
    monkeypatch.setattr(config, "EMBEDDINGS", "modelo-prueba")
    monkeypatch.setattr(embeddings, "_fallo_hasta", 0.0)

    class Lento:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): raise httpx.ReadTimeout("lento")
    monkeypatch.setattr(embeddings.httpx, "AsyncClient", Lento)
    assert correr(embeddings.vectores(["hola"], espera=1.5, castigar_lentitud=False)) is None
    assert embeddings._fallo_hasta == 0.0                       # el chat sigue intentándolo en el siguiente mensaje
    assert correr(embeddings.vectores(["hola"])) is None
    assert embeddings._fallo_hasta > 0                          # el rellenado en segundo plano sí espera 10 min
