"""Acceso por invitación: solicitudes desde la página pública /acceso y límites por persona.

Flujo: alguien rellena /acceso → queda una solicitud «pendiente» y se avisa a los administradores (Telegram) →
un administrador la aprueba con un perfil (o la rechaza) → se crea un usuario con rol `usuario`, sin contraseña,
y su email se añade al grupo de invitados de Cloudflare Access (`cf_access`). Entra con el código de un solo uso que
Cloudflare envía a su email; ARIA le reconoce por ese email.

Los límites se suman a los del rol `usuario` (que ya no ve nada de administración): qué secciones ve, cuántos mensajes
e imágenes al día, si su voz es la local (para no gastar la cuota de Gemini), memoria, Telegram, rutinas y cuándo
caduca el acceso. Un usuario sin fila en `invitados` no tiene límites extra (la familia de siempre).
"""
import hashlib
import hmac
import json
import re
import secrets
import time
from contextlib import closing

from . import config, db, tiempo, usuarios

SECCIONES = ("inicio", "chat", "finanzas", "informacion", "agenda", "mapa", "hud")
PERFILES = {
    "visita": {"nombre": "Visita", "secciones": ["inicio", "chat", "informacion", "mapa"], "mensajes_dia": 20,
               "imagenes_dia": 0, "voz": "local", "busqueda": True, "memoria": False, "telegram": False,
               "rutinas": False, "dias": 7},
    "familiar": {"nombre": "Familiar", "secciones": list(SECCIONES), "mensajes_dia": 200, "imagenes_dia": 20,
                 "voz": "completa", "busqueda": True, "memoria": True, "telegram": True, "rutinas": True, "dias": 0},
}
PERFIL_DEFECTO = "visita"
VOCES = ("completa", "local", "no")

MAX_PENDIENTES = 20          # solicitudes pendientes a la vez (más: «vuelve a intentarlo más tarde»)
MAX_POR_IP_DIA = 3
RETENCION_SOLICITUDES_DIAS = 30
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}")

# Rutas que un invitado puede usar siempre (además de las de sus secciones). El resto: según sus límites.
_SIEMPRE = [r"/", r"/logout", r"/static/.*", r"/api/info", r"/api/certificado", r"/api/voz/estado",
            r"/api/avisos.*", r"/api/recordatorios.*", r"/api/push/.*", r"/api/2fa.*", r"/api/agentes"]
_POR_SECCION = {
    "inicio": [r"/api/resumen-diario.*"],   # /api/briefing no: cuenta datos de la casa
    "chat": [r"/api/chat", r"/api/conversations.*", r"/api/vision/tickets/.*"],
    "finanzas": [r"/api/finanzas/.*"],
    "informacion": [r"/api/informacion/.*"],
    "agenda": [r"/api/agenda.*", r"/api/cumpleanos.*"],
    "mapa": [r"/api/mapa/.*"],
    "hud": [],
}
_POR_OPCION = {
    "memoria": [r"/api/memoria.*", r"/api/diario/.*", r"/api/proyectos.*", r"/api/decisiones/.*"],
    "telegram": [r"/api/telegram/.*"],
    "rutinas": [r"/api/rutinas.*"],
}
_VOZ = [r"/api/voz/(transcribir|hablar|despertar|voces|preferencias|muestra)"]

# Herramientas del chat para un invitado: consultas sin datos de casa. Se amplían según sus secciones y opciones.
HERRAMIENTAS_BASE = frozenset({"fecha_hora", "tiempo", "precio_luz", "noticias", "resumen_noticias", "resumir_enlace", "precio"})
HERRAMIENTAS_POR = {
    "busqueda": {"buscar_en_internet"},
    "mapa": {"mapa_ir", "ruta", "sitios_cerca"},
    "informacion": {"mis_mercados", "mis_inversiones"},
    "agenda": {"crear_evento", "mis_eventos", "borrar_evento", "anadir_cumpleanos", "proximos_cumpleanos",
               "recordatorio", "mis_recordatorios", "borrar_recordatorio"},
    "memoria": {"recordar", "olvidar"},
    "rutinas": {"crear_rutina", "mis_rutinas", "borrar_rutina"},
    "finanzas": {"resumen_mes", "gastos_por_categoria", "comparar_meses", "estado_presupuestos", "buscar_movimientos",
                 "registrar_movimiento"},
}


class AccesoError(Exception):
    """Mensaje legible para quien pide acceso o para el administrador."""


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS invitados (
                user_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
                perfil TEXT NOT NULL, limites TEXT NOT NULL, caduca REAL, creado REAL NOT NULL, aprobado_por INTEGER);
            CREATE TABLE IF NOT EXISTS solicitudes_acceso (
                id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL UNIQUE, nombre TEXT NOT NULL,
                email TEXT NOT NULL, motivo TEXT NOT NULL, ip TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','aprobada','rechazada')),
                creado REAL NOT NULL, resuelto REAL, user_id INTEGER, perfil TEXT);
            CREATE INDEX IF NOT EXISTS idx_solic_estado ON solicitudes_acceso(estado, creado);
            CREATE TABLE IF NOT EXISTS uso_invitados (
                user_id INTEGER NOT NULL, fecha TEXT NOT NULL, mensajes INTEGER NOT NULL DEFAULT 0,
                imagenes INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, fecha));
        """)


# --- Límites ---------------------------------------------------------------------------------------------------------
def normalizar_limites(d: dict | None, base: str = PERFIL_DEFECTO) -> dict:
    """Mezcla lo recibido con el perfil base y descarta lo que no sea válido."""
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in PERFILES.get(base, PERFILES[PERFIL_DEFECTO]).items() if k != "nombre"}
    d = d if isinstance(d, dict) else {}
    if isinstance(d.get("secciones"), list):
        out["secciones"] = [s for s in SECCIONES if s in d["secciones"]] or ["inicio"]
    if "inicio" not in out["secciones"]:
        out["secciones"].insert(0, "inicio")
    for k, tope in (("mensajes_dia", 1000), ("imagenes_dia", 200), ("dias", 365)):
        v = d.get(k)
        if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= tope:
            out[k] = v
    if d.get("voz") in VOCES:
        out["voz"] = d["voz"]
    for k in ("busqueda", "memoria", "telegram", "rutinas"):
        if isinstance(d.get(k), bool):
            out[k] = d[k]
    return out


_cache: dict = {}   # uid -> (instante, fila | None): el middleware lo consulta en cada petición


def de(uid: int) -> dict | None:
    """Límites del usuario (None = sin límites extra). Incluye `perfil` y `caduca`."""
    c = _cache.get(uid)
    if c and time.monotonic() - c[0] < 10:
        return c[1]
    with closing(db._con()) as con:
        r = con.execute("SELECT perfil, limites, caduca FROM invitados WHERE user_id=?", (uid,)).fetchone()
    fila = None
    if r:
        fila = normalizar_limites(json.loads(r["limites"]), r["perfil"] if r["perfil"] in PERFILES else PERFIL_DEFECTO)
        fila.update({"perfil": r["perfil"], "caduca": r["caduca"]})
    _cache[uid] = (time.monotonic(), fila)
    return fila


def olvidar_cache(uid: int | None = None) -> None:
    if uid is None:
        _cache.clear()
    else:
        _cache.pop(uid, None)


def caducado(lim: dict | None, ahora: float | None = None) -> bool:
    return bool(lim and lim.get("caduca") and (ahora or time.time()) >= lim["caduca"])


def _patrones(lim: dict) -> list:
    pats = list(_SIEMPRE)
    for s in lim["secciones"]:
        pats += _POR_SECCION.get(s, [])
    for k, v in _POR_OPCION.items():
        if lim.get(k):
            pats += v
    if lim.get("voz") != "no":
        pats += _VOZ
    return pats


def permitido(lim: dict | None, ruta: str) -> bool:
    """¿Puede un invitado con estos límites usar esta ruta? (el rol ya se comprobó antes; esto solo recorta)."""
    if lim is None:
        return True
    if caducado(lim):
        return False
    return any(re.fullmatch(p, ruta) for p in _patrones(lim))


def herramientas(lim: dict) -> frozenset:
    """Herramientas del chat que puede usar un invitado (se cruzan además con las del rol)."""
    h = set(HERRAMIENTAS_BASE)
    for clave in ("busqueda", "memoria", "rutinas"):
        if lim.get(clave):
            h |= HERRAMIENTAS_POR[clave]
    for s in ("mapa", "informacion", "agenda", "finanzas"):
        if s in lim["secciones"]:
            h |= HERRAMIENTAS_POR[s]
    return frozenset(h)


def publico(lim: dict | None) -> dict | None:
    """Lo que necesita la interfaz para esconder lo que no puede usar."""
    if lim is None:
        return None
    return {k: lim[k] for k in ("perfil", "secciones", "mensajes_dia", "imagenes_dia", "voz", "memoria", "telegram",
                                "rutinas", "caduca")}


def gastar(uid: int, lim: dict | None, tipo: str = "mensajes") -> int | None:
    """Apunta un uso de hoy y devuelve cuántos quedan (None = sin límite). Lanza AccesoError si ya no quedan."""
    if lim is None:
        return None
    tope = lim["mensajes_dia" if tipo == "mensajes" else "imagenes_dia"]
    hoy = tiempo.hoy().isoformat()
    col = "mensajes" if tipo == "mensajes" else "imagenes"
    with closing(db._con()) as con, con:
        con.execute("INSERT OR IGNORE INTO uso_invitados (user_id, fecha) VALUES (?,?)", (uid, hoy))
        usado = con.execute(f"SELECT {col} FROM uso_invitados WHERE user_id=? AND fecha=?", (uid, hoy)).fetchone()[0]
        if usado >= tope:
            raise AccesoError("Has llegado al límite de hoy: " + (
                f"{tope} mensajes." if tipo == "mensajes" else f"{tope} imágenes." if tope else "tu acceso no incluye imágenes."))
        con.execute(f"UPDATE uso_invitados SET {col}={col}+1 WHERE user_id=? AND fecha=?", (uid, hoy))
        con.execute("DELETE FROM uso_invitados WHERE fecha < ?", (tiempo.hoy().replace(day=1).isoformat(),))
    return tope - usado - 1


# --- Solicitudes ----------------------------------------------------------------------------------------------------
def huella_ip(ip: str) -> str:
    return hmac.new(config.SECRET.encode(), (ip or "?").encode(), hashlib.sha256).hexdigest()[:24]


def _texto(v, maximo: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f<>]", " ", str(v or "")).strip()[:maximo]


def solicitar(nombre, email, motivo, ip: str) -> dict:
    """Nueva solicitud pendiente. Devuelve {"token", "id"}; el token deja consultar su estado."""
    nombre, motivo = _texto(nombre, 60), _texto(motivo, 400)
    email = str(email or "").strip().lower()[:254]
    if len(nombre) < 2:
        raise AccesoError("Escribe tu nombre.")
    if not _EMAIL.fullmatch(email):
        raise AccesoError("El email no parece válido.")
    if len(motivo) < 5:
        raise AccesoError("Cuenta en una frase quién eres o para qué quieres entrar.")
    ahora, ip_h = time.time(), huella_ip(ip)
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM solicitudes_acceso WHERE creado < ? AND estado != 'pendiente'",
                    (ahora - RETENCION_SOLICITUDES_DIAS * 86400,))
        if con.execute("SELECT COUNT(*) FROM solicitudes_acceso WHERE ip=? AND creado > ?", (ip_h, ahora - 86400)).fetchone()[0] >= MAX_POR_IP_DIA:
            raise AccesoError("Ya has enviado varias solicitudes hoy. Prueba mañana.")
        if con.execute("SELECT COUNT(*) FROM solicitudes_acceso WHERE estado='pendiente'").fetchone()[0] >= MAX_PENDIENTES:
            raise AccesoError("Ahora mismo hay muchas solicitudes pendientes. Prueba más tarde.")
        previa = con.execute("SELECT token, id FROM solicitudes_acceso WHERE email=? AND estado='pendiente'", (email,)).fetchone()
        if previa:
            return {"token": previa["token"], "id": previa["id"], "repetida": True}
        token = secrets.token_urlsafe(18)
        cur = con.execute("INSERT INTO solicitudes_acceso (token, nombre, email, motivo, ip, creado) VALUES (?,?,?,?,?,?)",
                          (token, nombre, email, motivo, ip_h, ahora))
    return {"token": token, "id": cur.lastrowid, "repetida": False}


def estado_publico(token: str) -> dict | None:
    """Estado de una solicitud para quien la hizo (sin datos de nadie más)."""
    if not re.fullmatch(r"[\w-]{20,40}", token or ""):
        return None
    with closing(db._con()) as con:
        r = con.execute("SELECT estado, nombre FROM solicitudes_acceso WHERE token=?", (token,)).fetchone()
    return {"estado": r["estado"], "nombre": r["nombre"]} if r else None


def solicitud(sid: int) -> dict | None:
    with closing(db._con()) as con:
        r = con.execute("SELECT id, nombre, email, motivo, estado, creado, resuelto, perfil FROM solicitudes_acceso WHERE id=?",
                        (sid,)).fetchone()
    return dict(r) if r else None


def pendientes() -> list:
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute("SELECT id, nombre, email, motivo, creado FROM solicitudes_acceso "
                                             "WHERE estado='pendiente' ORDER BY creado")]


def aprobar(sid: int, perfil: str = PERFIL_DEFECTO, limites: dict | None = None, admin_id: int | None = None) -> dict:
    """Crea (o reactiva) el usuario con sus límites. Devuelve {"usuario", "solicitud"}. Cloudflare va aparte."""
    s = solicitud(sid)
    if not s:
        raise AccesoError("Esa solicitud no existe.")
    if s["estado"] != "pendiente":
        raise AccesoError(f"Esa solicitud ya está {s['estado']}.")
    if perfil not in PERFILES:
        raise AccesoError("Perfil desconocido.")
    u = usuarios.por_email(s["email"])
    if u and u["rol"] == "admin":
        raise AccesoError("Ese email ya es de un administrador.")
    if u is None:
        u = usuarios.crear(s["email"], s["nombre"], "usuario")
    elif not u["activo"]:
        u = usuarios.actualizar(u["id"], activo=True)
    fijar(u["id"], perfil, limites, admin_id)
    with closing(db._con()) as con, con:
        con.execute("UPDATE solicitudes_acceso SET estado='aprobada', resuelto=?, user_id=?, perfil=? WHERE id=?",
                    (time.time(), u["id"], perfil, sid))
    return {"usuario": usuarios.por_id(u["id"]), "solicitud": solicitud(sid)}


def rechazar(sid: int) -> dict:
    s = solicitud(sid)
    if not s:
        raise AccesoError("Esa solicitud no existe.")
    if s["estado"] != "pendiente":
        raise AccesoError(f"Esa solicitud ya está {s['estado']}.")
    with closing(db._con()) as con, con:
        con.execute("UPDATE solicitudes_acceso SET estado='rechazada', resuelto=? WHERE id=?", (time.time(), sid))
    return solicitud(sid)


def fijar(uid: int, perfil: str, limites: dict | None = None, admin_id: int | None = None, dias: int | None = None) -> dict:
    """Pone (o cambia) el perfil y los límites de un usuario. `dias` (o los del perfil) marcan la caducidad."""
    lim = normalizar_limites(limites, perfil)
    d = lim["dias"] if dias is None else dias
    caduca = time.time() + d * 86400 if d else None
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO invitados (user_id, perfil, limites, caduca, creado, aprobado_por) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET perfil=excluded.perfil, limites=excluded.limites, caduca=excluded.caduca",
                    (uid, perfil, json.dumps(lim), caduca, time.time(), admin_id))
    olvidar_cache(uid)
    return de(uid)


def quitar_limites(uid: int) -> None:
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM invitados WHERE user_id=?", (uid,))
    olvidar_cache(uid)


def listar() -> list:
    with closing(db._con()) as con:
        filas = con.execute("SELECT i.user_id, i.perfil, i.caduca, u.email, u.nombre, u.activo, u.ultimo_acceso "
                            "FROM invitados i JOIN usuarios u ON u.id = i.user_id ORDER BY u.nombre COLLATE NOCASE").fetchall()
    return [{**dict(r), "activo": bool(r["activo"]), "limites": publico(de(r["user_id"]))} for r in filas]


def revocar(uid: int) -> dict:
    """Desactiva al invitado (sus datos se conservan; se puede volver a aprobar). Cloudflare va aparte."""
    u = usuarios.por_id(uid)
    if not u or not de(uid):
        raise AccesoError("Ese usuario no es un invitado.")
    usuarios.actualizar(uid, activo=False)
    olvidar_cache(uid)
    return usuarios.por_id(uid)


def vencidos(ahora: float | None = None) -> list:
    """Invitados activos cuyo acceso ha caducado (para desactivarlos y sacarlos de Cloudflare)."""
    ahora = ahora or time.time()
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute(
            "SELECT i.user_id, u.email, u.nombre FROM invitados i JOIN usuarios u ON u.id = i.user_id "
            "WHERE u.activo=1 AND i.caduca IS NOT NULL AND i.caduca <= ?", (ahora,))]
