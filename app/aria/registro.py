"""Registro de las herramientas invocadas por ARIA."""
import contextvars
import json
import logging
import time
from contextlib import closing, contextmanager

from . import db

log = logging.getLogger("aria.registro")
ORIGEN = contextvars.ContextVar("aria_origen", default="chat")
_ORIGENES = {"chat", "telegram", "rutina", "automatizacion", "propuesta", "otro"}
_SECRETOS = ("password", "clave", "secret", "token", "pin", "codigo")


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS registro_herramientas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
                user_id INTEGER,
                rol TEXT NOT NULL, agente TEXT, origen TEXT NOT NULL CHECK (origen IN ('chat','telegram','rutina','automatizacion','propuesta','otro')),
                herramienta TEXT NOT NULL, args TEXT NOT NULL, ok INTEGER NOT NULL,
                resultado TEXT NOT NULL, ms INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_registro_ts ON registro_herramientas(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_registro_usuario_ts ON registro_herramientas(user_id, ts DESC);
        """)


@contextmanager
def origen(nombre: str):
    token = ORIGEN.set(nombre if nombre in _ORIGENES else "otro")
    try:
        yield
    finally:
        ORIGEN.reset(token)


def limpiar_args(args):
    if not isinstance(args, dict):
        return {}
    out = {}
    for clave, valor in list(args.items())[:20]:
        if str(clave).lower() == "uid":
            continue
        if any(s in str(clave).lower() for s in _SECRETOS):
            out[str(clave)] = "***"
        elif isinstance(valor, str):
            out[str(clave)] = valor[:200]
        else:
            out[str(clave)] = valor
    return out


def anotar(user_id, rol, agente, herramienta, args, ok, resultado, ms) -> None:
    try:
        with closing(db._con()) as con, con:
            con.execute(
                "INSERT INTO registro_herramientas "
                "(ts,user_id,rol,agente,origen,herramienta,args,ok,resultado,ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (time.time(), user_id, rol, agente, ORIGEN.get(), herramienta,
                 json.dumps(limpiar_args(args), ensure_ascii=False, default=str), int(bool(ok)),
                 str(resultado or "")[:300], int(ms)),
            )
    except Exception:  # noqa: BLE001 - el registro nunca debe romper la herramienta
        log.exception("No se pudo guardar el registro de la herramienta")


def listar(user_id=None, herramienta=None, solo_errores=False, limite=100) -> list:
    limite = max(1, min(int(limite), 500))
    sql = ("SELECT r.*, u.nombre AS usuario FROM registro_herramientas r "
           "LEFT JOIN usuarios u ON u.id=r.user_id WHERE 1=1")
    params = []
    if user_id is not None:
        sql += " AND r.user_id=?"; params.append(user_id)
    if herramienta:
        sql += " AND r.herramienta=?"; params.append(herramienta)
    if solo_errores:
        sql += " AND r.ok=0"
    sql += " ORDER BY r.ts DESC LIMIT ?"; params.append(limite)
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute(sql, params)]


def herramientas_usadas() -> list:
    with closing(db._con()) as con:
        return [r[0] for r in con.execute("SELECT DISTINCT herramienta FROM registro_herramientas ORDER BY herramienta")]


def purgar() -> None:
    try:
        with closing(db._con()) as con, con:
            con.execute("DELETE FROM registro_herramientas WHERE ts<?", (time.time() - 30 * 86400,))
            con.execute("DELETE FROM registro_herramientas WHERE id NOT IN "
                        "(SELECT id FROM registro_herramientas ORDER BY ts DESC, id DESC LIMIT 20000)")
    except Exception:  # noqa: BLE001
        log.exception("No se pudo purgar el registro de herramientas")
