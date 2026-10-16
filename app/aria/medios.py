"""Progreso de reproducción de archivos que permanecen en el navegador."""
import math
import re
import time
from contextlib import closing

from . import db

_H = re.compile(r"^[0-9a-f]{64}$")
MAX_FILAS = 3000


class MedioError(Exception):
    pass


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS medios_progreso (
            user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            huella TEXT NOT NULL, nombre TEXT NOT NULL, posicion REAL NOT NULL,
            duracion REAL NOT NULL, visto INTEGER NOT NULL DEFAULT 0, ts REAL NOT NULL,
            PRIMARY KEY(user_id, huella));
        CREATE INDEX IF NOT EXISTS idx_medios_usuario_ts ON medios_progreso(user_id, ts);
        """)


def _huella(h):
    if not isinstance(h, str) or not _H.fullmatch(h):
        raise MedioError("La huella no es válida.")
    return h


def _numero(v, nombre):
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise MedioError(f"{nombre} no es válido.")
    if not math.isfinite(n) or n < 0:
        raise MedioError(f"{nombre} no es válido.")
    return n


def guardar(uid, huella, nombre, posicion, duracion):
    h = _huella(huella)
    n = str(nombre or "").strip()
    if not n or len(n) > 200:
        raise MedioError("El nombre debe tener entre 1 y 200 caracteres.")
    p, d = _numero(posicion, "La posición"), _numero(duracion, "La duración")
    p = min(p, d) if d else p
    ahora = time.time()
    visto = int(d > 0 and p / d >= .9)
    with closing(db._con()) as con, con:
        con.execute("""INSERT INTO medios_progreso(user_id,huella,nombre,posicion,duracion,visto,ts)
                      VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,huella) DO UPDATE SET
                      nombre=excluded.nombre,posicion=excluded.posicion,duracion=excluded.duracion,
                      visto=excluded.visto,ts=excluded.ts""", (uid, h, n, p, d, visto, ahora))
        con.execute("""DELETE FROM medios_progreso WHERE user_id=? AND huella NOT IN
                     (SELECT huella FROM medios_progreso WHERE user_id=? ORDER BY ts DESC LIMIT ?)""",
                    (uid, uid, MAX_FILAS))
        return dict(con.execute("SELECT * FROM medios_progreso WHERE user_id=? AND huella=?", (uid, h)).fetchone())


def listar(uid, huellas=()):
    hs = [_huella(h) for h in huellas[:500]]
    if not hs:
        return []
    with closing(db._con()) as con:
        q = "SELECT * FROM medios_progreso WHERE user_id=? AND huella IN (%s)" % ",".join("?" * len(hs))
        return [dict(r) for r in con.execute(q, [uid, *hs])]
