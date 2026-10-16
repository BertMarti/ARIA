"""Listas compartidas de casa y listas privadas por usuario."""
import re
import time
from contextlib import closing

from . import db, invitados, memoria

MAX_LISTAS = 50
MAX_ITEMS = 300


class ListaError(Exception):
    """Error de validación o permisos de listas."""


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS listas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL CHECK(length(nombre) <= 60),
                icono TEXT NOT NULL DEFAULT '📋' CHECK(length(icono) <= 4), propietario INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                compartida_con TEXT NOT NULL DEFAULT 'solo_yo' CHECK(compartida_con IN ('todos','solo_yo')),
                creada REAL NOT NULL, orden INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS lista_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, lista_id INTEGER NOT NULL REFERENCES listas(id) ON DELETE CASCADE,
                texto TEXT NOT NULL CHECK(length(texto) <= 120), cantidad TEXT NOT NULL DEFAULT '' CHECK(length(cantidad) <= 20),
                hecho INTEGER NOT NULL DEFAULT 0 CHECK(hecho IN (0,1)), autor INTEGER NOT NULL REFERENCES usuarios(id),
                creado REAL NOT NULL, hecho_por INTEGER REFERENCES usuarios(id), hecho_en REAL);
            CREATE INDEX IF NOT EXISTS idx_listas_propietario ON listas(propietario);
            CREATE INDEX IF NOT EXISTS idx_lista_items_lista ON lista_items(lista_id, hecho, id);
        """)


def _texto(valor, limite, nombre):
    texto = str(valor or "").strip()
    if not texto:
        raise ListaError(f"{nombre} no puede estar vacío.")
    if len(texto) > limite:
        raise ListaError(f"{nombre} no puede superar {limite} caracteres.")
    return texto


def _uid_valido(uid: int) -> None:
    if invitados.de(uid):
        raise ListaError("Las listas no están disponibles para invitados.")


def _acceso(con, uid: int, lista_id: int, admin: bool = False, escribir: bool = False):
    r = con.execute("SELECT * FROM listas WHERE id=?", (lista_id,)).fetchone()
    if not r:
        return None
    if r["compartida_con"] == "todos" or r["propietario"] == uid:
        return r
    return None   # las listas «solo yo» son privadas: ni un administrador las ve ni las toca


def _fila(con, lista_id: int) -> dict:
    lista = dict(con.execute("SELECT * FROM listas WHERE id=?", (lista_id,)).fetchone())
    lista["items"] = [dict(x) for x in con.execute(
        "SELECT i.*, u.nombre AS autor_nombre FROM lista_items i JOIN usuarios u ON u.id=i.autor "
        "WHERE i.lista_id=? ORDER BY i.hecho, i.creado, i.id", (lista_id,))]
    lista["pendientes"] = sum(not x["hecho"] for x in lista["items"])
    return lista


def _partes(texto) -> list:
    bruto = str(texto or "").strip()
    partes = re.split(r"\s*(?:,|\by\b|\be\b)\s*", bruto, flags=re.IGNORECASE)
    return [p.strip() for p in partes if p.strip()]


def crear(uid: int, nombre, icono="📋", compartida_con="solo_yo") -> dict:
    _uid_valido(uid)
    nombre = _texto(nombre, 60, "El nombre")
    icono = _texto(icono, 4, "El icono")
    if compartida_con not in ("todos", "solo_yo"):
        raise ListaError("La visibilidad no es válida.")
    ahora = time.time()
    with closing(db._con()) as con, con:
        if con.execute("SELECT COUNT(*) FROM listas WHERE propietario=?", (uid,)).fetchone()[0] >= MAX_LISTAS:
            raise ListaError(f"No puedes tener más de {MAX_LISTAS} listas.")
        if not con.execute("SELECT 1 FROM listas").fetchone() and memoria.normalizar(nombre) != "la compra":
            con.execute("INSERT INTO listas(nombre,icono,propietario,compartida_con,creada,orden) VALUES(?,?,?,?,?,?)",
                        ("La compra", "🛒", uid, "todos", ahora, 0))
        lid = con.execute("INSERT INTO listas(nombre,icono,propietario,compartida_con,creada,orden) VALUES(?,?,?,?,?,?)",
                          (nombre, icono, uid, compartida_con, ahora, 0)).lastrowid
        return _fila(con, lid)


def listar(uid: int) -> list:
    _uid_valido(uid)
    with closing(db._con()) as con, con:
        if not con.execute("SELECT 1 FROM listas LIMIT 1").fetchone():   # la primera vez: «La compra» de toda la casa
            con.execute("INSERT INTO listas(nombre,icono,propietario,compartida_con,creada,orden) VALUES(?,?,?,?,?,?)",
                        ("La compra", "🛒", uid, "todos", time.time(), 0))
        filas = con.execute("SELECT id FROM listas WHERE compartida_con='todos' OR propietario=? "
                            "ORDER BY orden, nombre COLLATE NOCASE", (uid,)).fetchall()
        return [_fila(con, r["id"]) for r in filas]


def obtener(uid: int, lista_id: int) -> dict | None:
    _uid_valido(uid)
    with closing(db._con()) as con:
        return _fila(con, lista_id) if _acceso(con, uid, lista_id) else None


def renombrar(uid: int, lista_id: int, nombre, icono=None, admin=False) -> dict | None:
    nombre = _texto(nombre, 60, "El nombre")
    with closing(db._con()) as con, con:
        r = _acceso(con, uid, lista_id, admin, True)
        if not r or (r["propietario"] != uid and not admin):
            return None
        if icono is None:
            con.execute("UPDATE listas SET nombre=? WHERE id=?", (nombre, lista_id))
        else:
            con.execute("UPDATE listas SET nombre=?, icono=? WHERE id=?", (nombre, _texto(icono, 4, "El icono"), lista_id))
        return _fila(con, lista_id)


def borrar(uid: int, lista_id: int, admin=False) -> bool:
    with closing(db._con()) as con, con:
        r = con.execute("SELECT propietario, compartida_con FROM listas WHERE id=?", (lista_id,)).fetchone()
        # Un admin solo puede borrar listas de casa ajenas; las privadas solo su dueño (o al borrar su cuenta).
        if not r or (r["propietario"] != uid and not (admin and r["compartida_con"] == "todos")):
            return False
        return con.execute("DELETE FROM listas WHERE id=?", (lista_id,)).rowcount > 0


def anadir_items(uid: int, lista_id: int, texto, cantidad="", admin=False) -> list:
    _uid_valido(uid)
    partes = _partes(texto)
    if not partes:
        raise ListaError("Escribe al menos un artículo.")
    cantidad = str(cantidad or "").strip()[:20]
    ahora = time.time()
    with closing(db._con()) as con, con:
        if not _acceso(con, uid, lista_id, admin, True):
            return []
        abiertos = {memoria.normalizar(r["texto"]): r["id"] for r in con.execute(
            "SELECT id,texto FROM lista_items WHERE lista_id=? AND hecho=0", (lista_id,))}
        total = con.execute("SELECT COUNT(*) FROM lista_items WHERE lista_id=?", (lista_id,)).fetchone()[0]
        creados = []
        for parte in partes:
            texto_limpio = _texto(parte, 120, "El artículo")
            if memoria.normalizar(texto_limpio) in abiertos:
                continue
            if total >= MAX_ITEMS:
                raise ListaError(f"Una lista no puede tener más de {MAX_ITEMS} artículos.")
            iid = con.execute("INSERT INTO lista_items(lista_id,texto,cantidad,autor,creado) VALUES(?,?,?,?,?)",
                              (lista_id, texto_limpio, cantidad, uid, ahora)).lastrowid
            abiertos[memoria.normalizar(texto_limpio)] = iid
            total += 1
            creados.append(dict(con.execute("SELECT * FROM lista_items WHERE id=?", (iid,)).fetchone()))
        return creados


def marcar(uid: int, item_id: int, hecho=True, admin=False) -> dict | None:
    with closing(db._con()) as con, con:
        r = con.execute("SELECT i.*, l.compartida_con, l.propietario FROM lista_items i JOIN listas l ON l.id=i.lista_id WHERE i.id=?",
                        (item_id,)).fetchone()
        if not r or not _acceso(con, uid, r["lista_id"], admin, True):
            return None
        ahora = time.time() if hecho else None
        con.execute("UPDATE lista_items SET hecho=?, hecho_por=?, hecho_en=? WHERE id=?",
                    (int(hecho), uid if hecho else None, ahora, item_id))
        return dict(con.execute("SELECT * FROM lista_items WHERE id=?", (item_id,)).fetchone())


def borrar_item(uid: int, item_id: int, admin=False) -> bool:
    with closing(db._con()) as con, con:
        r = con.execute("SELECT lista_id FROM lista_items WHERE id=?", (item_id,)).fetchone()
        return bool(r and _acceso(con, uid, r["lista_id"], admin, True) and
                    con.execute("DELETE FROM lista_items WHERE id=?", (item_id,)).rowcount)


def vaciar_hechos(uid: int, lista_id: int, admin=False) -> int:
    with closing(db._con()) as con, con:
        if not _acceso(con, uid, lista_id, admin, True):
            return 0
        return con.execute("DELETE FROM lista_items WHERE lista_id=? AND hecho=1", (lista_id,)).rowcount


anadir = anadir_items
marcar_item = marcar
vaciar = vaciar_hechos
