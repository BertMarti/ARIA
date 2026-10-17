"""Documentos personales, extracción segura y búsqueda híbrida por usuario."""
import asyncio
import json
import logging
import os
import re
import resource
import subprocess
import sys
import time
import unicodedata
from array import array
from contextlib import closing
from pathlib import Path

from . import config, db, embeddings, memoria, premium

MAX_ARCHIVO = 15 * 1024 * 1024
MAX_PAGINAS = 400
MAX_CUOTA = 300 * 1024 * 1024
MAX_DOCUMENTOS = 200
MAX_TROZO = 1600
_EXT = {"pdf", "txt", "md"}
log = logging.getLogger("aria.documentos")
_tareas = set()


class DocumentoError(Exception):
    pass


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS documentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL CHECK(length(nombre) <= 150), tipo TEXT NOT NULL,
                tamano INTEGER NOT NULL, paginas INTEGER NOT NULL DEFAULT 0, creado REAL NOT NULL,
                estado TEXT NOT NULL CHECK(estado IN ('procesando','listo','error')),
                error TEXT CHECK(error IS NULL OR length(error) <= 200));
            CREATE INDEX IF NOT EXISTS idx_documentos_usuario ON documentos(user_id, creado DESC);
            CREATE TABLE IF NOT EXISTS documento_trozos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                pagina INTEGER NOT NULL, orden INTEGER NOT NULL,
                texto TEXT NOT NULL CHECK(length(texto) <= 1600), vector BLOB, modelo TEXT);
            CREATE INDEX IF NOT EXISTS idx_documento_trozos_doc ON documento_trozos(doc_id, orden);
        """)


def _nombre(nombre: str) -> tuple[str, str]:
    base = Path(str(nombre or "").replace("\\", "/")).name
    base = unicodedata.normalize("NFKC", base).replace("\x00", "").strip()
    ext = Path(base).suffix.lower().lstrip(".")
    stem = re.sub(r"[^\w .-]", "_", Path(base).stem, flags=re.UNICODE).strip(" .")
    if ext not in _EXT or not stem:
        raise DocumentoError("Solo se admiten archivos PDF, TXT o MD.")
    return (f"{stem[:145]}.{ext}", ext)


def _ruta(uid: int, doc_id: int, ext: str) -> Path:
    return config.DATA_DIR / "documentos" / str(uid) / f"{doc_id}.{ext}"


def _cuotas(con, uid: int) -> tuple[int, int]:
    fila = con.execute("SELECT COUNT(*), COALESCE(SUM(tamano), 0) FROM documentos WHERE user_id=?", (uid,)).fetchone()
    return int(fila[0]), int(fila[1])


def crear(uid: int, nombre: str, contenido: bytes) -> dict:
    nombre, ext = _nombre(nombre)
    if len(contenido) > MAX_ARCHIVO:
        raise DocumentoError("El archivo no puede superar 15 MB.")
    if ext == "pdf" and len(contenido) < 64:   # un PDF real nunca es tan pequeño (solo cabecera = basura)
        raise DocumentoError("El PDF está vacío o dañado.")
    if ext == "pdf" and not contenido.startswith(b"%PDF-"):
        raise DocumentoError("El archivo no tiene una cabecera PDF válida.")
    if ext != "pdf" and contenido.startswith(b"%PDF-"):
        raise DocumentoError("La extensión no coincide con el contenido.")
    with closing(db._con()) as con, con:
        n, bytes_ = _cuotas(con, uid)
        maximo = min(MAX_DOCUMENTOS, premium.limite("documentos") or MAX_DOCUMENTOS)
        if n >= maximo:
            if premium.limite("documentos") is not None:
                raise DocumentoError("Con ARIA Gratis puedes tener 20 documentos. Hazte Premium para tener más.")
            raise DocumentoError("No puedes tener más de 200 documentos.")
        if bytes_ + len(contenido) > MAX_CUOTA:
            raise DocumentoError("Has superado la cuota de 300 MB.")
        cur = con.execute("INSERT INTO documentos(user_id,nombre,tipo,tamano,creado,estado) VALUES(?,?,?,?,?,?)",
                          (uid, nombre, ext, len(contenido), time.time(), "procesando"))
        doc_id = cur.lastrowid
    ruta = _ruta(uid, doc_id, ext)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    try:
        ruta.write_bytes(contenido)
        ruta.chmod(0o600)
    except Exception:
        borrar(uid, doc_id)
        raise DocumentoError("No se pudo guardar el archivo.")
    return obtener(uid, doc_id)   # el procesado lo programa quien llama, desde el bucle asíncrono (crear va en un hilo)


def programar_documento(uid: int, doc: dict) -> None:
    """Desde código asíncrono: extrae y trocea en segundo plano el documento recién creado."""
    programar(uid, doc["id"], _ruta(uid, doc["id"], doc["tipo"]), doc["tipo"])


def _limitar_hijo():
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))


def _extraer(ruta: Path, ext: str) -> list[dict]:
    if ext != "pdf":
        return [{"pagina": 1, "texto": ruta.read_text(encoding="utf-8", errors="replace")}]
    # Por ruta y con -I: el extractor solo usa pypdf, sin importar nada de ARIA ni del directorio actual
    # (con «-I -m aria.…» Python no encontraba el paquete, que no está en site-packages).
    extractor = Path(__file__).resolve().with_name("documentos_extraer.py")
    p = subprocess.run([sys.executable, "-I", "-B", str(extractor), str(ruta)],   # -B: sin .pyc (RLIMIT_FSIZE=0)
                       capture_output=True, timeout=90, preexec_fn=_limitar_hijo, cwd="/", check=False)
    if len(p.stdout) > 20 * 1024 * 1024:
        raise DocumentoError("La extracción ha producido una salida demasiado grande.")
    if p.returncode or not p.stdout:
        raise DocumentoError("No se ha podido leer el PDF de forma segura.")
    datos = json.loads(p.stdout)
    if not isinstance(datos, list) or len(datos) > MAX_PAGINAS:
        raise DocumentoError("El PDF supera el límite de 400 páginas.")
    return [{"pagina": int(x["pagina"]), "texto": str(x.get("texto") or "")} for x in datos]


def _trocear(paginas: list[dict]) -> list[dict]:
    salida = []
    for pagina in paginas:
        texto = " ".join(str(pagina["texto"]).split())
        inicio = 0
        orden = 0
        while inicio < len(texto):
            fin = min(len(texto), inicio + 1200)
            salida.append({"pagina": pagina["pagina"], "orden": orden, "texto": texto[inicio:fin]})
            if fin == len(texto):
                break
            inicio = fin - 150
            orden += 1
    return salida


def _guardar_trozos(uid: int, doc_id: int, trozos: list[dict], paginas: int) -> None:
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM documento_trozos WHERE doc_id=?", (doc_id,))
        con.executemany("INSERT INTO documento_trozos(doc_id,user_id,pagina,orden,texto) VALUES(?,?,?,?,?)",
                        [(doc_id, uid, x["pagina"], x["orden"], x["texto"]) for x in trozos])
        con.execute("UPDATE documentos SET paginas=?, estado='listo', error=NULL WHERE id=? AND user_id=?",
                    (paginas, doc_id, uid))


def _error(uid: int, doc_id: int, mensaje: str) -> None:
    with closing(db._con()) as con, con:
        con.execute("UPDATE documentos SET estado='error', error=? WHERE id=? AND user_id=?", (mensaje[:200], doc_id, uid))


async def _procesar(uid: int, doc_id: int, ruta: Path, ext: str) -> None:
    try:
        paginas = await asyncio.to_thread(_extraer, ruta, ext)
        trozos = _trocear(paginas)
        await asyncio.to_thread(_guardar_trozos, uid, doc_id, trozos, len(paginas))
        if config.EMBEDDINGS:
            for inicio in range(0, len(trozos), 16):
                vs = await embeddings.vectores([x["texto"] for x in trozos[inicio:inicio + 16]])
                if not vs:
                    break
                with closing(db._con()) as con, con:
                    con.executemany("UPDATE documento_trozos SET vector=?, modelo=? WHERE doc_id=? AND pagina=? AND orden=?",
                                    [(array("f", v).tobytes(), config.EMBEDDINGS, doc_id, x["pagina"], x["orden"])
                                     for x, v in zip(trozos[inicio:inicio + 16], vs)])
    except subprocess.TimeoutExpired:
        _error(uid, doc_id, "La extracción ha superado los 90 segundos.")
    except Exception as exc:  # noqa: BLE001
        log.warning("Error procesando documento %s: %s", doc_id, exc)
        _error(uid, doc_id, "No se ha podido procesar el documento.")


def programar(uid: int, doc_id: int, ruta: Path, ext: str):
    tarea = asyncio.get_running_loop().create_task(_procesar(uid, doc_id, ruta, ext))
    _tareas.add(tarea)
    tarea.add_done_callback(_tareas.discard)


def _fila(r) -> dict:
    return dict(r) if r else None


def obtener(uid: int, doc_id: int) -> dict | None:
    with closing(db._con()) as con:
        return _fila(con.execute("SELECT id,nombre,tipo,tamano,paginas,creado,estado,error FROM documentos WHERE user_id=? AND id=?",
                                 (uid, doc_id)).fetchone())


def listar(uid: int) -> list:
    with closing(db._con()) as con:
        return [_fila(r) for r in con.execute("SELECT id,nombre,tipo,tamano,paginas,creado,estado,error FROM documentos WHERE user_id=? ORDER BY creado DESC, id DESC", (uid,))]


def ruta_archivo(uid: int, doc_id: int) -> tuple[dict, Path] | None:
    doc = obtener(uid, doc_id)
    if not doc:
        return None
    ruta = _ruta(uid, doc_id, doc["tipo"])
    return doc, ruta


def borrar(uid: int, doc_id: int) -> bool:
    item = ruta_archivo(uid, doc_id)
    if not item:
        return False
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM documentos WHERE user_id=? AND id=?", (uid, doc_id))
    try:
        item[1].unlink(missing_ok=True)
    except OSError:
        log.warning("No se pudo borrar el archivo del documento %s", doc_id)
    return True


def borrar_archivos(uid: int) -> None:
    carpeta = config.DATA_DIR / "documentos" / str(uid)
    if carpeta.exists():
        for ruta in carpeta.iterdir():
            if ruta.is_file():
                ruta.unlink(missing_ok=True)
        carpeta.rmdir()


def _puntuacion(pregunta: str, texto: str) -> float:
    p, t = memoria.palabras(pregunta), memoria.palabras(texto)
    return len(p & t) / max(len(p), 1)


async def buscar(uid: int, pregunta: str, k: int = 6, doc_id: int | None = None) -> list:
    pregunta = memoria.limpiar(pregunta)
    if not pregunta:
        return []
    with closing(db._con()) as con:
        sql = "SELECT t.*, d.nombre FROM documento_trozos t JOIN documentos d ON d.id=t.doc_id WHERE t.user_id=? AND d.estado='listo'"
        params = [uid]
        if doc_id is not None:
            sql += " AND t.doc_id=?"
            params.append(doc_id)
        filas = con.execute(sql, params).fetchall()
    consulta = await embeddings.vectores([pregunta], espera=1.5, castigar_lentitud=False)
    puntuados = []
    for fila in filas:
        palabras = _puntuacion(pregunta, fila["texto"])
        sem = embeddings.coseno(consulta[0], array("f", fila["vector"])) if consulta and fila["vector"] else 0
        puntuados.append((sem * 0.75 + palabras * 0.25, palabras, dict(fila)))
    puntuados.sort(key=lambda x: (-x[0], -x[1], x[2]["id"]))
    return [x[2] for x in puntuados[:max(1, min(k, 20))]]
