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


def _respaldar_antes_de_usuarios() -> None:
    """Copia de seguridad (data/aria.db.bak-sso) antes de la migración a varios usuarios."""
    ruta = _ruta()
    destino = ruta.with_name(ruta.name + ".bak-sso")
    if not ruta.exists() or destino.exists():
        return
    with closing(sqlite3.connect(ruta, timeout=10)) as origen:
        tablas = {r[0] for r in origen.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "conversaciones" not in tablas or "user_id" in {r[1] for r in origen.execute("PRAGMA table_info(conversaciones)")}:
            return
        with closing(sqlite3.connect(destino)) as dest:
            origen.backup(dest)
    destino.chmod(0o600)


def iniciar() -> None:
    _respaldar_antes_de_usuarios()
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
            -- Memoria a largo plazo (por usuario): datos recordados, diario y resumen de cada día.
            CREATE TABLE IF NOT EXISTS recuerdos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                texto TEXT NOT NULL CHECK (length(texto) <= 300),
                origen TEXT NOT NULL CHECK (origen IN ('usuario','auto')),
                creado REAL NOT NULL, usado REAL);
            CREATE INDEX IF NOT EXISTS idx_recuerdos_user ON recuerdos(user_id, creado DESC);
            CREATE TABLE IF NOT EXISTS diario (
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                fecha TEXT NOT NULL, resumen TEXT NOT NULL CHECK (length(resumen) <= 600),
                creado REAL NOT NULL, PRIMARY KEY (user_id, fecha));
            CREATE TABLE IF NOT EXISTS memoria_ajustes (
                user_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
                aprender INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS resumen_dia (
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                fecha TEXT NOT NULL, datos TEXT NOT NULL, saludado INTEGER NOT NULL DEFAULT 0,
                creado REAL NOT NULL, PRIMARY KEY (user_id, fecha));
            CREATE TABLE IF NOT EXISTS proyectos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL, descripcion TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'idea'
                    CHECK (estado IN ('idea','en_curso','pausado','terminado')), creado REAL NOT NULL, actualizado REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_proyectos_user ON proyectos(user_id, actualizado DESC);
            CREATE TABLE IF NOT EXISTS decisiones (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE, texto TEXT NOT NULL,
                motivo TEXT NOT NULL DEFAULT '', fecha REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_decisiones_proyecto ON decisiones(user_id, proyecto_id, fecha DESC);
        """)
        # Migración: etiqueta del cerebro que respondió (p. ej. "Ollama Cloud · gpt-oss:120b").
        if "cerebro" not in {r["name"] for r in con.execute("PRAGMA table_info(mensajes)")}:
            con.execute("ALTER TABLE mensajes ADD COLUMN cerebro TEXT")
        # Migración: cada conversación pertenece a un usuario (las antiguas se asignan al admin en usuarios.iniciar).
        if "user_id" not in {r["name"] for r in con.execute("PRAGMA table_info(conversaciones)")}:
            con.execute("ALTER TABLE conversaciones ADD COLUMN user_id INTEGER")
        # Migración: agente de la conversación (selector) y agente que respondió cada mensaje.
        if "agente" not in {r["name"] for r in con.execute("PRAGMA table_info(conversaciones)")}:
            con.execute("ALTER TABLE conversaciones ADD COLUMN agente TEXT")
        if "agente" not in {r["name"] for r in con.execute("PRAGMA table_info(mensajes)")}:
            con.execute("ALTER TABLE mensajes ADD COLUMN agente TEXT")
        if "modo" not in {r["name"] for r in con.execute("PRAGMA table_info(memoria_ajustes)")}:
            con.execute("ALTER TABLE memoria_ajustes ADD COLUMN modo TEXT NOT NULL DEFAULT 'amable'")
        if "discrepar" not in {r["name"] for r in con.execute("PRAGMA table_info(memoria_ajustes)")}:
            con.execute("ALTER TABLE memoria_ajustes ADD COLUMN discrepar INTEGER NOT NULL DEFAULT 0")
        con.execute("CREATE INDEX IF NOT EXISTS idx_conv_user ON conversaciones(user_id, actualizada DESC)")


def titulo_desde(texto: str) -> str:
    t = re.sub(r"\s+", " ", texto).strip()
    if len(t) <= MAX_TITULO:
        return t or "Conversación nueva"
    return t[:MAX_TITULO].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def crear(uid: int, titulo: str = "Conversación nueva") -> str:
    cid, ahora = secrets.token_urlsafe(9), time.time()
    with closing(_con()) as con, con:
        con.execute("INSERT INTO conversaciones (id, titulo, creada, actualizada, user_id) VALUES (?,?,?,?,?)",
                    (cid, titulo[:120], ahora, ahora, uid))
    return cid


def existe(cid: str, uid: int) -> bool:
    with closing(_con()) as con:
        return con.execute("SELECT 1 FROM conversaciones WHERE id=? AND user_id=?", (cid, uid)).fetchone() is not None


def listar(uid: int) -> list:
    with closing(_con()) as con:
        return [dict(r) for r in con.execute(
            "SELECT id, titulo, actualizada FROM conversaciones WHERE user_id=? "
            "ORDER BY actualizada DESC LIMIT 200", (uid,))]


def obtener(cid: str, uid: int) -> dict | None:
    with closing(_con()) as con:
        c = con.execute("SELECT id, titulo, agente FROM conversaciones WHERE id=? AND user_id=?", (cid, uid)).fetchone()
        if not c:
            return None
        msgs = [{"role": r["rol"], "content": r["contenido"], "cerebro": r["cerebro"], "agente": r["agente"]}
                for r in con.execute("SELECT rol, contenido, cerebro, agente FROM mensajes WHERE conv_id=? ORDER BY id", (cid,))]
    return {"id": c["id"], "titulo": c["titulo"], "agente": c["agente"] or "aria", "mensajes": msgs}


def fijar_agente(cid: str, uid: int, agente: str) -> bool:
    with closing(_con()) as con, con:
        return con.execute("UPDATE conversaciones SET agente=? WHERE id=? AND user_id=?", (agente, cid, uid)).rowcount > 0


def renombrar(cid: str, uid: int, titulo: str) -> bool:
    titulo = re.sub(r"\s+", " ", titulo).strip()[:120]
    if not titulo:
        return False
    with closing(_con()) as con, con:
        return con.execute("UPDATE conversaciones SET titulo=? WHERE id=? AND user_id=?", (titulo, cid, uid)).rowcount > 0


def borrar(cid: str, uid: int) -> bool:
    with closing(_con()) as con, con:
        return con.execute("DELETE FROM conversaciones WHERE id=? AND user_id=?", (cid, uid)).rowcount > 0


def borrar_de_usuario(uid: int) -> int:
    """Borra todas las conversaciones de un usuario (al eliminarlo)."""
    with closing(_con()) as con, con:
        return con.execute("DELETE FROM conversaciones WHERE user_id=?", (uid,)).rowcount


def anadir(cid: str, rol: str, contenido: str, cerebro: str | None = None, agente: str | None = None) -> None:
    """rol: user | assistant | tool (el contenido de 'tool' es JSON {name,args,text})."""
    ahora = time.time()
    with closing(_con()) as con, con:
        con.execute("INSERT INTO mensajes (conv_id, rol, contenido, ts, cerebro, agente) VALUES (?,?,?,?,?,?)",
                    (cid, rol, contenido, ahora, cerebro, agente))
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
    return json.dumps({"name": nombre, "args": args, "text": texto[:1600]}, ensure_ascii=False)
