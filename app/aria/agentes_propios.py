"""Agentes configurables por cada usuario."""
import json
import re
import time
from contextlib import closing

from . import db, tools

MAXIMO = 10
ICONOS = frozenset(("aria", "finanzas", "redes", "seguridad"))
_SLUG = re.compile(r"^[a-z0-9]{2,20}$")
LIMITE_MINUTO = 20
_ultimas: dict[int, list] = {}


class AgentePropioError(ValueError):
    pass


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS agentes_propios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            slug TEXT NOT NULL, nombre TEXT NOT NULL, icono TEXT NOT NULL,
            instrucciones TEXT NOT NULL, herramientas TEXT NOT NULL, creado REAL NOT NULL,
            UNIQUE(user_id, slug))""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_agentes_propios_user ON agentes_propios(user_id, creado)")


def _fila(r) -> dict:
    return {"id": r["id"], "slug": r["slug"], "nombre": r["nombre"], "icono": r["icono"],
            "instrucciones": r["instrucciones"], "herramientas": json.loads(r["herramientas"]), "creado": r["creado"]}


def _validar(datos: dict, rol: str, actual: int | None = None) -> dict:
    if not isinstance(datos, dict):
        raise AgentePropioError("Datos no válidos.")
    slug = datos.get("slug")
    nombre = datos.get("nombre")
    icono = datos.get("icono")
    instrucciones = datos.get("instrucciones", "")
    hs = datos.get("herramientas", [])
    if not isinstance(slug, str) or not _SLUG.fullmatch(slug):
        raise AgentePropioError("El atajo debe tener de 2 a 20 caracteres: solo minúsculas y números (sin espacios ni tildes).")
    if slug in {"aria", "finanzas", "redes", "seguridad"}:
        raise AgentePropioError("Ese atajo está reservado.")
    if not isinstance(nombre, str) or not 1 <= len(nombre.strip()) <= 40:
        raise AgentePropioError("El nombre debe tener entre 1 y 40 caracteres.")
    if icono not in ICONOS:
        raise AgentePropioError("Icono no válido.")
    if not isinstance(instrucciones, str) or len(instrucciones) > 1500:
        raise AgentePropioError("Las instrucciones no pueden superar 1500 caracteres.")
    permitidas = tools.permitidas(rol)
    if not isinstance(hs, list) or any(not isinstance(h, str) or h not in permitidas for h in hs):
        raise AgentePropioError("Hay una herramienta no permitida para tu rol.")
    return {"slug": slug, "nombre": nombre.strip(), "icono": icono,
            "instrucciones": instrucciones, "herramientas": sorted(set(hs))}


def _comprobar_limite(uid: int) -> None:
    """Como mucho LIMITE_MINUTO altas o cambios por persona y minuto."""
    ahora = time.monotonic()
    recientes = [t for t in _ultimas.get(uid, []) if ahora - t < 60]
    if len(recientes) >= LIMITE_MINUTO:
        raise AgentePropioError("Demasiados cambios seguidos. Espera un momento.")
    _ultimas[uid] = recientes + [ahora]


def listar(uid: int) -> list:
    with closing(db._con()) as con:
        return [_fila(r) for r in con.execute("SELECT * FROM agentes_propios WHERE user_id=? ORDER BY creado, id", (uid,))]


def obtener(uid: int, aid: int) -> dict | None:
    with closing(db._con()) as con:
        r = con.execute("SELECT * FROM agentes_propios WHERE id=? AND user_id=?", (aid, uid)).fetchone()
    return _fila(r) if r else None


def por_slug(uid: int, slug: str) -> dict | None:
    with closing(db._con()) as con:
        r = con.execute("SELECT * FROM agentes_propios WHERE slug=? AND user_id=?", (slug, uid)).fetchone()
    return _fila(r) if r else None


def crear(uid: int, rol: str, datos: dict) -> dict:
    d = _validar(datos, rol)
    _comprobar_limite(uid)
    with closing(db._con()) as con, con:
        if con.execute("SELECT COUNT(*) FROM agentes_propios WHERE user_id=?", (uid,)).fetchone()[0] >= MAXIMO:
            raise AgentePropioError("Solo puedes crear 10 agentes.")
        try:
            r = con.execute("INSERT INTO agentes_propios (user_id,slug,nombre,icono,instrucciones,herramientas,creado) VALUES (?,?,?,?,?,?,?)",
                            (uid, d["slug"], d["nombre"], d["icono"], d["instrucciones"], json.dumps(d["herramientas"]), time.time()))
        except Exception as e:
            if "UNIQUE" in str(e):
                raise AgentePropioError("Ya tienes un agente con ese atajo.") from e
            raise
        nuevo = r.lastrowid
    return obtener(uid, nuevo)   # ya confirmado: otra conexión lo ve


def actualizar(uid: int, rol: str, aid: int, datos: dict) -> dict | None:
    d = _validar(datos, rol, aid)
    _comprobar_limite(uid)
    with closing(db._con()) as con, con:
        if not con.execute("SELECT 1 FROM agentes_propios WHERE id=? AND user_id=?", (aid, uid)).fetchone():
            return None
        try:
            con.execute("UPDATE agentes_propios SET slug=?,nombre=?,icono=?,instrucciones=?,herramientas=? WHERE id=? AND user_id=?",
                        (d["slug"], d["nombre"], d["icono"], d["instrucciones"], json.dumps(d["herramientas"]), aid, uid))
        except Exception as e:
            if "UNIQUE" in str(e):
                raise AgentePropioError("Ya tienes un agente con ese atajo.") from e
            raise
    return obtener(uid, aid)


def borrar(uid: int, aid: int) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM agentes_propios WHERE id=? AND user_id=?", (aid, uid)).rowcount > 0
