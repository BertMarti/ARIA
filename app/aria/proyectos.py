"""Proyectos y decisiones personales, aislados por usuario."""
import time
from contextlib import closing

from . import db, memoria

ESTADOS = ("idea", "en_curso", "pausado", "terminado")
MAX_CONTEXTO = 900


class ProyectoError(Exception):
    pass


def _proyecto(r):
    return dict(r) if r else None


def listar(uid):
    with closing(db._con()) as con:
        return [_proyecto(r) for r in con.execute(
            "SELECT id, nombre, descripcion, estado, creado, actualizado FROM proyectos "
            "WHERE user_id=? ORDER BY actualizado DESC, id DESC", (uid,))]


def obtener(uid, pid):
    with closing(db._con()) as con:
        r = con.execute("SELECT id, nombre, descripcion, estado, creado, actualizado FROM proyectos WHERE user_id=? AND id=?",
                        (uid, pid)).fetchone()
    return _proyecto(r)


def crear(uid, nombre, descripcion="", estado="idea"):
    nombre = " ".join(str(nombre or "").split())[:120]
    descripcion = " ".join(str(descripcion or "").split())[:500]
    if len(nombre) < 2:
        raise ProyectoError("El proyecto necesita un nombre.")
    if estado not in ESTADOS:
        raise ProyectoError("Estado no válido.")
    ahora = time.time()
    with closing(db._con()) as con, con:
        cur = con.execute("INSERT INTO proyectos (user_id,nombre,descripcion,estado,creado,actualizado) VALUES (?,?,?,?,?,?)",
                          (uid, nombre, descripcion, estado, ahora, ahora))
    return obtener(uid, cur.lastrowid)


def actualizar(uid, pid, nombre=None, descripcion=None, estado=None):
    p = obtener(uid, pid)
    if not p:
        raise ProyectoError("Proyecto no encontrado.")
    nombre = p["nombre"] if nombre is None else " ".join(str(nombre).split())[:120]
    descripcion = p["descripcion"] if descripcion is None else " ".join(str(descripcion).split())[:500]
    estado = p["estado"] if estado is None else estado
    if len(nombre) < 2 or estado not in ESTADOS:
        raise ProyectoError("Datos del proyecto no válidos.")
    with closing(db._con()) as con, con:
        con.execute("UPDATE proyectos SET nombre=?, descripcion=?, estado=?, actualizado=? WHERE user_id=? AND id=?",
                    (nombre, descripcion, estado, time.time(), uid, pid))
    return obtener(uid, pid)


def borrar(uid, pid):
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM proyectos WHERE user_id=? AND id=?", (uid, pid)).rowcount > 0


def decisiones(uid, pid):
    if not obtener(uid, pid):
        raise ProyectoError("Proyecto no encontrado.")
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute(
            "SELECT id, proyecto_id, texto, motivo, fecha FROM decisiones WHERE user_id=? AND proyecto_id=? "
            "ORDER BY fecha DESC, id DESC", (uid, pid))]


def registrar_decision(uid, pid, texto, motivo=""):
    if not obtener(uid, pid):
        raise ProyectoError("Proyecto no encontrado.")
    texto, motivo = " ".join(str(texto or "").split())[:500], " ".join(str(motivo or "").split())[:500]
    if len(texto) < 2:
        raise ProyectoError("Escribe la decisión.")
    if memoria.parece_secreto(texto) or memoria.parece_secreto(motivo):
        raise ProyectoError("No guardo secretos en las decisiones.")
    with closing(db._con()) as con, con:
        cur = con.execute("INSERT INTO decisiones (user_id,proyecto_id,texto,motivo,fecha) VALUES (?,?,?,?,?)",
                          (uid, pid, texto, motivo, time.time()))
    return next(r for r in decisiones(uid, pid) if r["id"] == cur.lastrowid)


def borrar_decision(uid, did):
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM decisiones WHERE user_id=? AND id=?", (uid, did)).rowcount > 0


def contexto(uid, mensaje, nube):
    limite = MAX_CONTEXTO if nube else 300
    mensaje = str(mensaje or "").lower()
    for p in listar(uid):
        if p["nombre"].lower() not in mensaje:
            continue
        ds = decisiones(uid, p["id"])[:3]
        texto = f"Proyecto mencionado: {p['nombre']} ({p['estado']})."
        if p["descripcion"]:
            texto += f" {p['descripcion']}"
        if ds:
            texto += " Decisiones recientes: " + "; ".join(d["texto"] for d in ds) + "."
        return memoria._recortar(texto, limite)
    return ""
