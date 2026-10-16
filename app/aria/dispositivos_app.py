"""Tokens de dispositivo para la aplicación nativa, sin guardar secretos."""
import hashlib
import hmac
import re
import secrets
import time
from contextlib import closing

from . import db, usuarios

_FORMATO = re.compile(r"^ariad_[A-Za-z0-9_-]{43}$")
CADUCIDAD = 180 * 86400


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS app_dispositivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            nombre TEXT NOT NULL CHECK(length(nombre) <= 60),
            huella TEXT NOT NULL UNIQUE,
            creado REAL NOT NULL,
            ultimo_uso REAL,
            caduca REAL NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_app_dispositivos_user ON app_dispositivos(user_id, creado)")


def _nombre(nombre) -> str:
    return " ".join(str(nombre or "").split())[:60] or "Móvil"


def crear(uid: int, nombre) -> dict:
    iniciar()
    token = "ariad_" + secrets.token_urlsafe(32)
    ahora = time.time()
    caduca = ahora + CADUCIDAD
    huella = hashlib.sha256(token.encode()).hexdigest()
    with closing(db._con()) as con, con:
        viejos = con.execute("SELECT id FROM app_dispositivos WHERE user_id=? ORDER BY creado ASC", (uid,)).fetchall()
        if len(viejos) >= 10:
            con.execute("DELETE FROM app_dispositivos WHERE id=?", (viejos[0]["id"],))
        ident = con.execute("INSERT INTO app_dispositivos(user_id,nombre,huella,creado,caduca) VALUES(?,?,?,?,?)",
                            (uid, _nombre(nombre), huella, ahora, caduca)).lastrowid
    return {"id": ident, "token": token, "caduca": caduca}


def verificar(token: str) -> dict | None:
    if not isinstance(token, str) or not _FORMATO.fullmatch(token):
        return None
    huella = hashlib.sha256(token.encode()).hexdigest()
    ahora = time.time()
    with closing(db._con()) as con:
        fila = con.execute("SELECT * FROM app_dispositivos WHERE huella=?", (huella,)).fetchone()
        if not fila or not hmac.compare_digest(fila["huella"], huella) or fila["caduca"] <= ahora:
            return None
        u = usuarios.por_id(fila["user_id"])
        if not u or not u["activo"]:
            return None
        if fila["ultimo_uso"] is None or ahora - fila["ultimo_uso"] >= 60:
            con.execute("UPDATE app_dispositivos SET ultimo_uso=? WHERE id=?", (ahora, fila["id"]))
    return u


def listar(uid: int) -> list:
    iniciar()
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute(
            "SELECT id, nombre, creado, ultimo_uso, caduca FROM app_dispositivos WHERE user_id=? ORDER BY creado DESC", (uid,))]


def revocar(uid: int, ident: int) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM app_dispositivos WHERE id=? AND user_id=?", (ident, uid)).rowcount > 0
