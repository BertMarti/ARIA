"""Conversaciones persistentes en SQLite (data/aria.db, solo biblioteca estándar)."""
import json
import re
import secrets
import sqlite3
import time
from contextlib import closing

from . import config

MAX_TITULO = 60


def _ruta():
    return config.DATA_DIR / "aria.db"


def _con() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_ruta(), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def iniciar() -> None:
    with closing(_con()) as con, con:
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                id TEXT PRIMARY KEY, titulo TEXT NOT NULL,
                creada REAL NOT NULL, actualizada REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conv_id TEXT NOT NULL REFERENCES conversaciones(id) ON DELETE CASCADE,
                rol TEXT NOT NULL, contenido TEXT NOT NULL, ts REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_mensajes_conv ON mensajes(conv_id, id);
            CREATE INDEX IF NOT EXISTS idx_conv_act ON conversaciones(actualizada DESC);
        """)
        # Migración: etiqueta del cerebro que respondió (p. ej. "Ollama Cloud · gpt-oss:120b").
        if "cerebro" not in {r["name"] for r in con.execute("PRAGMA table_info(mensajes)")}:
            con.execute("ALTER TABLE mensajes ADD COLUMN cerebro TEXT")


def titulo_desde(texto: str) -> str:
    t = re.sub(r"\s+", " ", texto).strip()
    if len(t) <= MAX_TITULO:
        return t or "Conversación nueva"
    return t[:MAX_TITULO].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def crear(titulo: str = "Conversación nueva") -> str:
    cid, ahora = secrets.token_urlsafe(9), time.time()
    with closing(_con()) as con, con:
        con.execute("INSERT INTO conversaciones VALUES (?,?,?,?)", (cid, titulo[:120], ahora, ahora))
    return cid


def existe(cid: str) -> bool:
    with closing(_con()) as con:
        return con.execute("SELECT 1 FROM conversaciones WHERE id=?", (cid,)).fetchone() is not None


def listar() -> list:
    with closing(_con()) as con:
        return [dict(r) for r in con.execute(
            "SELECT id, titulo, actualizada FROM conversaciones ORDER BY actualizada DESC LIMIT 200")]


def obtener(cid: str) -> dict | None:
    with closing(_con()) as con:
        c = con.execute("SELECT id, titulo FROM conversaciones WHERE id=?", (cid,)).fetchone()
        if not c:
            return None
        msgs = [{"role": r["rol"], "content": r["contenido"], "cerebro": r["cerebro"]} for r in con.execute(
            "SELECT rol, contenido, cerebro FROM mensajes WHERE conv_id=? ORDER BY id", (cid,))]
    return {"id": c["id"], "titulo": c["titulo"], "mensajes": msgs}


def renombrar(cid: str, titulo: str) -> bool:
    titulo = re.sub(r"\s+", " ", titulo).strip()[:120]
    if not titulo:
        return False
    with closing(_con()) as con, con:
        return con.execute("UPDATE conversaciones SET titulo=? WHERE id=?", (titulo, cid)).rowcount > 0


def borrar(cid: str) -> bool:
    with closing(_con()) as con, con:
        return con.execute("DELETE FROM conversaciones WHERE id=?", (cid,)).rowcount > 0


def anadir(cid: str, rol: str, contenido: str, cerebro: str | None = None) -> None:
    """rol: user | assistant | tool (el contenido de 'tool' es JSON {name,args,text})."""
    ahora = time.time()
    with closing(_con()) as con, con:
        con.execute("INSERT INTO mensajes (conv_id, rol, contenido, ts, cerebro) VALUES (?,?,?,?,?)",
                    (cid, rol, contenido, ahora, cerebro))
        con.execute("UPDATE conversaciones SET actualizada=? WHERE id=?", (ahora, cid))


def es_primer_mensaje(cid: str) -> bool:
    with closing(_con()) as con:
        return con.execute("SELECT 1 FROM mensajes WHERE conv_id=? LIMIT 1", (cid,)).fetchone() is None


def historial_modelo(cid: str, maximo: int) -> list:
    """Últimos mensajes user/assistant (para el contexto del modelo)."""
    with closing(_con()) as con:
        filas = con.execute(
            "SELECT rol, contenido FROM mensajes WHERE conv_id=? AND rol IN ('user','assistant') "
            "ORDER BY id DESC LIMIT ?", (cid, maximo)).fetchall()
    return [{"role": r["rol"], "content": r["contenido"]} for r in reversed(filas)]


def herramienta_json(nombre: str, args: dict, texto: str = "") -> str:
    return json.dumps({"name": nombre, "args": args, "text": texto[:500]}, ensure_ascii=False)
