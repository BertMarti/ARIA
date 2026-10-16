import asyncio
from pathlib import Path

import pytest

from aria import config, db, documentos, embeddings, usuarios


def _iniciar():
    documentos.iniciar()
    return usuarios.por_identificador("admin")


def test_validacion_cabecera_nombre_y_tamano():
    usuario = _iniciar()
    with pytest.raises(documentos.DocumentoError):
        documentos.crear(usuario["id"], "../manual.pdf", b"no es pdf")
    with pytest.raises(documentos.DocumentoError):
        documentos.crear(usuario["id"], "manual.pdf", b"%PDF-")
    with pytest.raises(documentos.DocumentoError):
        documentos.crear(usuario["id"], "manual.pdf", b"%PDF-" + b"x" * documentos.MAX_ARCHIVO)


def test_troceado_con_solape():
    trozos = documentos._trocear([{"pagina": 3, "texto": "a" * 2400}])
    assert len(trozos) == 3
    assert trozos[1]["texto"][:150] == trozos[0]["texto"][-150:]


def test_cuotas_documentos_y_aislamiento(monkeypatch):
    uno = _iniciar()
    otro = usuarios.crear("docs@example.com", "Otro", "usuario", "clave-larga-docs")
    monkeypatch.setattr(documentos, "programar", lambda *args: None)
    doc = documentos.crear(uno["id"], "manual.txt", b"contrato de prueba")
    assert documentos.obtener(otro["id"], doc["id"]) is None
    assert documentos.ruta_archivo(otro["id"], doc["id"]) is None
    assert not documentos.borrar(otro["id"], doc["id"])
    assert documentos.borrar(uno["id"], doc["id"])
    assert not (config.DATA_DIR / "documentos" / str(uno["id"]) / "1.txt").exists()


def test_busqueda_por_palabras_sin_ollama(monkeypatch):
    uid = _iniciar()["id"]
    monkeypatch.setattr(documentos, "programar", lambda *args: None)
    doc = documentos.crear(uid, "contrato.txt", b"La fianza vence en marzo de 2027.")
    with db._con() as con:
        con.execute("UPDATE documentos SET estado='listo', paginas=1 WHERE id=?", (doc["id"],))
        con.execute("INSERT INTO documento_trozos(doc_id,user_id,pagina,orden,texto) VALUES(?,?,?,?,?)",
                    (doc["id"], uid, 1, 0, "La fianza vence en marzo de 2027."))
    monkeypatch.setattr(embeddings, "vectores", lambda *args, **kwargs: asyncio.sleep(0, result=None))
    resultados = asyncio.run(documentos.buscar(uid, "¿Cuándo vence la fianza?"))
    assert resultados and resultados[0]["nombre"] == "contrato.txt"
    assert resultados[0]["pagina"] == 1


def test_extraccion_pdf_y_pdf_invalido(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    ruta = Path(tmp_path) / "minimo.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(200, 200)
    with ruta.open("wb") as archivo:
        writer.write(archivo)
    assert documentos._extraer(ruta, "pdf")[0]["pagina"] == 1
    malo = Path(tmp_path) / "malo.pdf"
    malo.write_bytes(b"no es un pdf")
    with pytest.raises(documentos.DocumentoError):
        documentos._extraer(malo, "pdf")
