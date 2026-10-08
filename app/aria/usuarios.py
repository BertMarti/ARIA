"""Usuarios de ARIA (tabla `usuarios` de data/aria.db): roles, altas, bajas y sesiones por usuario."""
import re
import time
from contextlib import closing

from . import auth, config, db

ROLES = ("admin", "usuario")
MAX_NOMBRE = 40
_EMAIL = re.compile(r"^[^@\s<>\"',;]{1,64}@[^@\s<>\"',;]+\.[^@\s<>\"',;]{2,}$")

_CAMPOS = "id, email, usuario, nombre, rol, activo, pass_hash, version, creado, ultimo_acceso"


class UsuarioError(Exception):
    """Error de validación o de regla de negocio (el mensaje va en español y se muestra tal cual)."""


def _fila(r, interno: bool = False) -> dict | None:
    if r is None:
        return None
    d = {"id": r["id"], "email": r["email"], "usuario": r["usuario"], "nombre": r["nombre"], "rol": r["rol"],
         "activo": bool(r["activo"]), "version": r["version"], "creado": r["creado"],
         "ultimo_acceso": r["ultimo_acceso"], "tiene_password": bool(r["pass_hash"]) or _es_admin_env(r),
         "protegido": r["email"] in config.ADMIN_EMAILS}
    if interno:
        d["pass_hash"] = r["pass_hash"]
    return d


def _es_admin_env(r) -> bool:
    """El admin heredado sigue entrando con ARIA_PASSWORD hasta que cambie su contraseña."""
    return bool(config.USER and config.PASSWORD and r["usuario"] == config.USER.lower() and not r["pass_hash"])


def iniciar() -> None:
    """Crea la tabla y migra al admin único (usuario `admin`, su contraseña y sus conversaciones)."""
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            usuario TEXT UNIQUE,
            nombre TEXT NOT NULL,
            rol TEXT NOT NULL CHECK (rol IN ('admin','usuario')),
            activo INTEGER NOT NULL DEFAULT 1,
            pass_hash TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            creado REAL NOT NULL,
            ultimo_acceso REAL)""")
        nombre_admin = (config.USER or "").strip().lower()
        if not nombre_admin:
            return
        fila = con.execute("SELECT id FROM usuarios WHERE usuario=?", (nombre_admin,)).fetchone()
        if fila is None:
            legado = auth.leer_legado()
            email = config.ADMIN_EMAILS[0] if config.ADMIN_EMAILS else f"{nombre_admin}@aria.local"
            if con.execute("SELECT 1 FROM usuarios WHERE email=?", (email,)).fetchone():
                email = f"{nombre_admin}@aria.local"
            h = legado.get("hash") if isinstance(legado.get("hash"), str) else None
            v = legado.get("version") if isinstance(legado.get("version"), int) else 1
            cur = con.execute(
                "INSERT INTO usuarios (email, usuario, nombre, rol, activo, pass_hash, version, creado) "
                "VALUES (?,?,?,?,1,?,?,?)",
                (email, nombre_admin, config.NOMBRE_USUARIO or "Administrador", "admin", h, v, time.time()))
            admin_id = cur.lastrowid
        else:
            admin_id = fila["id"]
        con.execute("UPDATE conversaciones SET user_id=? WHERE user_id IS NULL", (admin_id,))
        _fusionar_alias(con)


def canonico(email: str) -> str:
    """Todos los emails de ARIA_ADMIN_EMAILS son la misma persona: se usa el primero."""
    e = (email or "").strip().lower()
    return config.ADMIN_EMAILS[0] if config.ADMIN_EMAILS and e in config.ADMIN_EMAILS else e


def _fusionar_alias(con) -> None:
    """Si un email secundario de ARIA_ADMIN_EMAILS tiene usuario propio, se une al principal
    (sus conversaciones pasan al principal y el usuario duplicado desaparece)."""
    if len(config.ADMIN_EMAILS) < 2:
        return
    principal = con.execute("SELECT id FROM usuarios WHERE email=?", (config.ADMIN_EMAILS[0],)).fetchone()
    for alias in config.ADMIN_EMAILS[1:]:
        fila = con.execute("SELECT id FROM usuarios WHERE email=?", (alias,)).fetchone()
        if fila is None:
            continue
        if principal is None:
            con.execute("UPDATE usuarios SET email=? WHERE id=?", (config.ADMIN_EMAILS[0], fila["id"]))
            principal = fila
            continue
        if fila["id"] != principal["id"]:
            con.execute("UPDATE conversaciones SET user_id=? WHERE user_id=?", (principal["id"], fila["id"]))
            con.execute("DELETE FROM usuarios WHERE id=?", (fila["id"],))


# --- Consultas ---
def _uno(sql: str, args: tuple, interno: bool = False) -> dict | None:
    with closing(db._con()) as con:
        return _fila(con.execute(f"SELECT {_CAMPOS} FROM usuarios WHERE {sql}", args).fetchone(), interno)


def por_id(uid, interno: bool = False) -> dict | None:
    return _uno("id=?", (uid,), interno) if isinstance(uid, int) and not isinstance(uid, bool) else None


def por_email(email: str, interno: bool = False) -> dict | None:
    return _uno("email=?", ((email or "").strip().lower(),), interno)


def por_identificador(ident: str, interno: bool = False) -> dict | None:
    """Email o nombre de usuario (sin distinguir mayúsculas)."""
    i = canonico(ident)
    return _uno("email=? OR usuario=?", (i, i), interno) if i else None


def listar() -> list:
    with closing(db._con()) as con:
        return [_fila(r) for r in con.execute(f"SELECT {_CAMPOS} FROM usuarios ORDER BY rol, nombre COLLATE NOCASE, id")]


def _admins_activos(con) -> int:
    return con.execute("SELECT COUNT(*) FROM usuarios WHERE rol='admin' AND activo=1").fetchone()[0]


# --- Validación ---
def email_valido(email) -> str:
    e = (email or "").strip().lower() if isinstance(email, str) else ""
    if len(e) > 254 or not _EMAIL.match(e):
        raise UsuarioError("El email no es válido.")
    return e


def nombre_limpio(nombre, email: str = "") -> str:
    n = " ".join(str(nombre or "").split())[:MAX_NOMBRE]
    return n or email.split("@")[0][:MAX_NOMBRE] or "Usuario"


def _rol(rol) -> str:
    if rol not in ROLES:
        raise UsuarioError("El rol debe ser «admin» o «usuario».")
    return rol


def _comprobar_password(p) -> str:
    if not isinstance(p, str) or len(p) < auth.MIN_PASSWORD:
        raise UsuarioError(f"La contraseña debe tener al menos {auth.MIN_PASSWORD} caracteres.")
    if len(p) > 200:
        raise UsuarioError("La contraseña es demasiado larga.")
    return p


# --- Altas, cambios y bajas ---
def crear(email, nombre, rol="usuario", password=None) -> dict:
    e, r = email_valido(email), _rol(rol)
    h = auth.hashear(_comprobar_password(password)) if password else None
    try:
        with closing(db._con()) as con, con:
            cur = con.execute(
                "INSERT INTO usuarios (email, nombre, rol, activo, pass_hash, version, creado) VALUES (?,?,?,1,?,1,?)",
                (e, nombre_limpio(nombre, e), r, h, time.time()))
    except db.sqlite3.IntegrityError:
        raise UsuarioError("Ya existe un usuario con ese email.") from None
    return por_id(cur.lastrowid)


def por_sso(email: str) -> dict | None:
    """Usuario ARIA para una identidad ya verificada de Cloudflare Access (None = no tiene acceso).

    Los emails de ARIA_ADMIN_EMAILS son siempre administradores activos y se crean en su primer acceso."""
    e = canonico(email)
    if e in config.ADMIN_EMAILS:
        u = por_email(e)
        if u is None:
            try:
                crear(e, config.NOMBRE_USUARIO or e.split("@")[0], "admin")
            except UsuarioError:
                pass
            u = por_email(e)
        elif u["rol"] != "admin" or not u["activo"]:
            with closing(db._con()) as con, con:
                con.execute("UPDATE usuarios SET rol='admin', activo=1 WHERE id=?", (u["id"],))
            u = por_email(e)
        return u
    u = por_email(e)
    return u if u and u["activo"] else None


def tocar_acceso(uid: int) -> None:
    with closing(db._con()) as con, con:
        con.execute("UPDATE usuarios SET ultimo_acceso=? WHERE id=?", (time.time(), uid))


def actualizar(uid: int, rol=None, activo=None, nombre=None) -> dict:
    u = por_id(uid)
    if not u:
        raise UsuarioError("Usuario no encontrado.")
    with closing(db._con()) as con, con:
        quita_admin = u["rol"] == "admin" and u["activo"] and (
            (rol is not None and rol != "admin") or (activo is not None and not activo))
        if quita_admin:
            if u["protegido"]:
                raise UsuarioError("Ese email figura en ARIA_ADMIN_EMAILS: siempre es administrador.")
            if _admins_activos(con) <= 1:
                raise UsuarioError("No se puede quitar al último administrador activo.")
        if rol is not None:
            con.execute("UPDATE usuarios SET rol=? WHERE id=?", (_rol(rol), uid))
        if nombre is not None:
            con.execute("UPDATE usuarios SET nombre=? WHERE id=?", (nombre_limpio(nombre, u["email"]), uid))
        if activo is not None:
            # Al desactivar o reactivar cambia la versión: las sesiones anteriores dejan de valer.
            con.execute("UPDATE usuarios SET activo=?, version=version+1 WHERE id=?", (1 if activo else 0, uid))
    return por_id(uid)


def borrar(uid: int) -> None:
    u = por_id(uid)
    if not u:
        raise UsuarioError("Usuario no encontrado.")
    if u["protegido"]:
        raise UsuarioError("Ese email figura en ARIA_ADMIN_EMAILS: no se puede eliminar.")
    with closing(db._con()) as con, con:
        if u["rol"] == "admin" and u["activo"] and _admins_activos(con) <= 1:
            raise UsuarioError("No se puede eliminar al último administrador activo.")
        con.execute("DELETE FROM conversaciones WHERE user_id=?", (uid,))
        for t in ("fin_movimientos", "fin_categorias", "fin_presupuestos", "fin_reglas"):  # sus finanzas
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone():
                con.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))  # noqa: S608 - nombres fijos
        con.execute("DELETE FROM usuarios WHERE id=?", (uid,))


# --- Contraseñas (para entrar desde casa) ---
def fijar_password(uid: int, nueva) -> None:
    """Pone la contraseña (sin pedir la actual: lo usa el administrador) y cierra las sesiones del usuario."""
    h = auth.hashear(_comprobar_password(nueva))
    with closing(db._con()) as con, con:
        if con.execute("UPDATE usuarios SET pass_hash=?, version=version+1 WHERE id=?", (h, uid)).rowcount == 0:
            raise UsuarioError("Usuario no encontrado.")


def quitar_password(uid: int) -> None:
    with closing(db._con()) as con, con:
        con.execute("UPDATE usuarios SET pass_hash=NULL, version=version+1 WHERE id=?", (uid,))


def password_correcta(u: dict | None, password: str) -> bool:
    """Compara en tiempo constante; sin usuario o sin contraseña hace igualmente un hash falso."""
    if u is None:
        auth.verificar_hash(password, auth.HASH_FALSO)
        return False
    h = u.get("pass_hash")
    if h:
        return auth.verificar_hash(password, h)
    if config.USER and config.PASSWORD and u["usuario"] == config.USER.lower():
        return auth.igual(password, config.PASSWORD)
    auth.verificar_hash(password, auth.HASH_FALSO)
    return False


def autenticar(ident: str, password: str) -> dict | None:
    """Login de casa: email o usuario + contraseña. Devuelve el usuario activo o None."""
    u = por_identificador(ident, interno=True)
    ok = password_correcta(u, password)
    if not (ok and u and u["activo"]):
        return None
    u.pop("pass_hash", None)
    return u


def cambiar_password(uid: int, actual: str, nueva: str, repetida: str) -> str | None:
    """Cambio de la propia contraseña. Devuelve un mensaje de error (en español) o None si se cambió."""
    u = por_id(uid, interno=True)
    if not u:
        return "Usuario no encontrado."
    tiene = bool(u["pass_hash"]) or _es_admin_env(u)
    if tiene and not password_correcta(u, actual):
        return "La contraseña actual no es correcta."
    if nueva != repetida:
        return "Las contraseñas nuevas no coinciden."
    if len(nueva) < auth.MIN_PASSWORD:
        return f"La contraseña nueva debe tener al menos {auth.MIN_PASSWORD} caracteres."
    if tiene and nueva == actual:
        return "La contraseña nueva debe ser distinta de la actual."
    fijar_password(uid, nueva)
    return None
