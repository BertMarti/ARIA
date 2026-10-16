"""Notas personales, separadas de la memoria y de los recordatorios."""
import json
import re
import time
from contextlib import closing
from datetime import datetime

from . import config, db, usuarios

MAX_TEXTO = 1000
MAX_NOTAS = 500
CATEGORIAS = ("general", "mejora", "compra", "idea")
ESTADOS = ("abierta", "hecha")
ORIGENES = ("web", "telegram", "chat")


class NotaError(Exception):
    """Error de validación legible para la interfaz y el modelo."""


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS notas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                texto TEXT NOT NULL CHECK(length(texto) <= 1000),
                categoria TEXT NOT NULL DEFAULT 'general' CHECK(categoria IN ('general','mejora','compra','idea')),
                estado TEXT NOT NULL DEFAULT 'abierta' CHECK(estado IN ('abierta','hecha')),
                origen TEXT NOT NULL DEFAULT 'web' CHECK(origen IN ('web','telegram','chat')),
                creado REAL NOT NULL, actualizado REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_notas_usuario ON notas(user_id, estado, categoria);
        """)


def _texto(texto) -> str:
    t = str(texto or "").strip()
    if not t:
        raise NotaError("La nota no puede estar vacía.")
    if len(t) > MAX_TEXTO:
        raise NotaError(f"La nota no puede superar {MAX_TEXTO} caracteres.")
    return t


def _opcion(valor, opciones, nombre):
    v = str(valor or "").strip().lower()
    if v not in opciones:
        raise NotaError(f"La {nombre} debe ser una de: {', '.join(opciones)}.")
    return v


def _fila(r) -> dict:
    return dict(r)


def exportar_mejoras() -> None:
    carpeta = config.DATA_DIR / "host"
    carpeta.mkdir(parents=True, exist_ok=True)
    with closing(db._con()) as con:
        filas = con.execute("SELECT n.id, n.texto, n.creado, n.origen FROM notas n "
                            "JOIN usuarios u ON u.id=n.user_id WHERE n.categoria='mejora' "
                            "AND n.estado='abierta' AND u.rol='admin' ORDER BY n.creado, n.id").fetchall()
    datos = [{"id": r["id"], "texto": r["texto"], "creado": datetime.fromtimestamp(r["creado"]).isoformat(),
              "origen": r["origen"]} for r in filas]
    destino = carpeta / "notas-mejoras.json"
    temporal = destino.with_suffix(".json.tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporal.replace(destino)


def crear(uid: int, texto, categoria="general", origen="web") -> dict:
    t, cat, org = _texto(texto), _opcion(categoria, CATEGORIAS, "categoría"), _opcion(origen, ORIGENES, "origen")
    ahora = time.time()
    with closing(db._con()) as con, con:
        if con.execute("SELECT COUNT(*) FROM notas WHERE user_id=?", (uid,)).fetchone()[0] >= MAX_NOTAS:
            raise NotaError(f"No puedes tener más de {MAX_NOTAS} notas.")
        nid = con.execute("INSERT INTO notas(user_id,texto,categoria,origen,creado,actualizado) VALUES(?,?,?,?,?,?)",
                          (uid, t, cat, org, ahora, ahora)).lastrowid
        nota = _fila(con.execute("SELECT * FROM notas WHERE id=?", (nid,)).fetchone())
    if cat == "mejora":
        exportar_mejoras()
    return nota


def crear_varias(uid: int, texto, categoria="general", origen="web") -> list:
    bruto = str(texto or "").strip()
    partes = [x.strip() for x in re.split(r"(?:^|\n)\s*[-*•]\s+", bruto) if x.strip()]
    return [crear(uid, x, categoria, origen) for x in (partes or [bruto])]


def listar(uid: int, estado=None, categoria=None) -> list:
    args = [uid]
    sql = "SELECT * FROM notas WHERE user_id=?"
    if estado:
        sql += " AND estado=?"; args.append(_opcion(estado, ESTADOS, "estado"))
    if categoria:
        sql += " AND categoria=?"; args.append(_opcion(categoria, CATEGORIAS, "categoría"))
    sql += " ORDER BY estado='hecha', actualizado DESC, id DESC"
    with closing(db._con()) as con:
        return [_fila(r) for r in con.execute(sql, args)]


def editar(uid: int, nid: int, texto=None, categoria=None, estado=None) -> dict | None:
    cambios, args = [], []
    if texto is not None: cambios += ["texto=?"]; args.append(_texto(texto))
    if categoria is not None: cambios += ["categoria=?"]; args.append(_opcion(categoria, CATEGORIAS, "categoría"))
    if estado is not None: cambios += ["estado=?"]; args.append(_opcion(estado, ESTADOS, "estado"))
    if not cambios: raise NotaError("No hay cambios que guardar.")
    cambios.append("actualizado=?"); args.append(time.time()); args += [nid, uid]
    with closing(db._con()) as con, con:
        r = con.execute("SELECT * FROM notas WHERE id=? AND user_id=?", (nid, uid)).fetchone()
        if not r: return None
        con.execute("UPDATE notas SET " + ",".join(cambios) + " WHERE id=? AND user_id=?", args)
        nota = _fila(con.execute("SELECT * FROM notas WHERE id=?", (nid,)).fetchone())
    if r["categoria"] == "mejora" or nota["categoria"] == "mejora": exportar_mejoras()
    return nota


def borrar(uid: int, nid: int) -> bool:
    with closing(db._con()) as con, con:
        r = con.execute("SELECT categoria FROM notas WHERE id=? AND user_id=?", (nid, uid)).fetchone()
        if not r: return False
        con.execute("DELETE FROM notas WHERE id=? AND user_id=?", (nid, uid))
    if r["categoria"] == "mejora": exportar_mejoras()
    return True
