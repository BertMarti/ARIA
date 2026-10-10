"""Proactividad con permiso: ARIA propone acciones y no hace nada hasta que la persona las aprueba.

Los generadores miran el día (luz, agenda, red) y dejan propuestas en una bandeja por usuario: título, explicación y
la herramienta que se ejecutaría con sus argumentos. Al aprobar, se ejecuta con el rol de quien aprueba (las mismas
comprobaciones que en el chat); al rechazar o caducar, no pasa nada. Las ve en Inicio y, si tiene Telegram, con botones.

Solo se pueden proponer herramientas de `PROPONIBLES`: acciones pequeñas, reversibles y sin coste.
"""
import json
import logging
import time
from contextlib import closing
from datetime import datetime, timedelta

from . import config, db, tiempo

log = logging.getLogger("aria.propuestas")

# Herramienta que se puede proponer -> cómo empieza su respuesta cuando ha ido bien
PROPONIBLES = {"recordatorio": "Recordatorio ", "marcar_dispositivo_conocido": "Dispositivo "}
MAX_PENDIENTES = 10
RETENCION_DIAS = 30
ESTADOS = ("pendiente", "ejecutando", "aprobada", "rechazada", "caducada", "fallida")


class PropuestaError(Exception):
    """Mensaje legible."""


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS propuestas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                clave TEXT NOT NULL, tipo TEXT NOT NULL, titulo TEXT NOT NULL, detalle TEXT NOT NULL,
                herramienta TEXT NOT NULL, args TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente', resultado TEXT,
                creado REAL NOT NULL, caduca REAL NOT NULL, resuelto REAL,
                UNIQUE (user_id, clave));
            CREATE INDEX IF NOT EXISTS idx_propuestas_user ON propuestas(user_id, estado, creado);
        """)


def _fila(r) -> dict:
    d = dict(r)
    d["args"] = json.loads(d["args"])
    return d


def crear(uid: int, clave: str, tipo: str, titulo: str, detalle: str, herramienta: str, args: dict,
          caduca: float) -> dict | None:
    """Deja una propuesta pendiente (None si ya se propuso esto mismo o la bandeja está llena)."""
    if herramienta not in PROPONIBLES:
        raise PropuestaError(f"«{herramienta}» no se puede proponer.")
    ahora = time.time()
    if caduca <= ahora:
        return None
    with closing(db._con()) as con, con:
        if con.execute("SELECT 1 FROM propuestas WHERE user_id=? AND clave=?", (uid, clave)).fetchone():
            return None
        if con.execute("SELECT COUNT(*) FROM propuestas WHERE user_id=? AND estado='pendiente'", (uid,)).fetchone()[0] >= MAX_PENDIENTES:
            return None
        cur = con.execute("INSERT INTO propuestas (user_id, clave, tipo, titulo, detalle, herramienta, args, creado, caduca) "
                          "VALUES (?,?,?,?,?,?,?,?,?)",
                          (uid, clave, tipo, titulo[:120], detalle[:400], herramienta, json.dumps(args, ensure_ascii=False), ahora, caduca))
        return _fila(con.execute("SELECT * FROM propuestas WHERE id=?", (cur.lastrowid,)).fetchone())


def caducar(ahora: float | None = None) -> int:
    ahora = ahora or time.time()
    with closing(db._con()) as con, con:
        n = con.execute("UPDATE propuestas SET estado='caducada', resuelto=? WHERE estado='pendiente' AND caduca<=?",
                        (ahora, ahora)).rowcount
        con.execute("DELETE FROM propuestas WHERE creado < ?", (ahora - RETENCION_DIAS * 86400,))
    return n


def listar(uid: int, solo_pendientes: bool = True, limite: int = 30) -> list:
    caducar()
    sql = "SELECT * FROM propuestas WHERE user_id=?" + (" AND estado='pendiente'" if solo_pendientes else "")
    with closing(db._con()) as con:
        return [_fila(r) for r in con.execute(sql + " ORDER BY creado DESC LIMIT ?", (uid, max(1, min(100, limite))))]


def obtener(uid: int, pid: int) -> dict | None:
    with closing(db._con()) as con:
        r = con.execute("SELECT * FROM propuestas WHERE id=? AND user_id=?", (pid, uid)).fetchone()
    return _fila(r) if r else None


def _resolver(pid: int, estado: str, resultado: str | None = None) -> None:
    with closing(db._con()) as con, con:
        con.execute("UPDATE propuestas SET estado=?, resultado=?, resuelto=? WHERE id=? AND estado IN ('pendiente','ejecutando')",
                    (estado, (resultado or "")[:400] or None, time.time(), pid))


def _reclamar(pid: int, uid: int) -> bool:
    """Pasa la propuesta a «ejecutando» de forma atómica: si dos aprobaciones llegan a la vez, solo una gana."""
    with closing(db._con()) as con, con:
        return con.execute("UPDATE propuestas SET estado='ejecutando' WHERE id=? AND user_id=? AND estado='pendiente'",
                           (pid, uid)).rowcount == 1


async def decidir(usuario: dict, pid: int, aprobar: bool) -> dict:
    """Aprueba (ejecuta) o rechaza una propuesta propia. Devuelve la propuesta actualizada."""
    import asyncio
    from . import tools
    await asyncio.to_thread(caducar)
    p = await asyncio.to_thread(obtener, usuario["id"], pid)
    if not p:
        raise PropuestaError("Esa propuesta no existe.")
    if p["estado"] != "pendiente":
        raise PropuestaError(f"Esa propuesta ya está {p['estado']}.")
    if not aprobar:
        await asyncio.to_thread(_resolver, pid, "rechazada")
        return await asyncio.to_thread(obtener, usuario["id"], pid)
    if not await asyncio.to_thread(_reclamar, pid, usuario["id"]):
        raise PropuestaError("Esa propuesta ya se está atendiendo.")
    if p["herramienta"] not in PROPONIBLES:   # p. ej. una propuesta antigua de algo que ya no se puede proponer
        await asyncio.to_thread(_resolver, pid, "fallida", "Esa acción ya no se puede hacer desde una propuesta.")
        return await asyncio.to_thread(obtener, usuario["id"], pid)
    try:
        res = await _ejecutar(tools, p, usuario)
    except Exception:  # noqa: BLE001 - que nunca se quede en «ejecutando»
        log.exception("Falló una propuesta aprobada")
        res = "Error al ejecutar la propuesta."
    fallo = not res.startswith(PROPONIBLES[p["herramienta"]])
    await asyncio.to_thread(_resolver, pid, "fallida" if fallo else "aprobada", res)
    return await asyncio.to_thread(obtener, usuario["id"], pid)


async def _ejecutar(tools, p: dict, usuario: dict) -> str:
    try:
        from . import registro   # registro de herramientas (si existe): origen «propuesta»
        with registro.origen("propuesta"):
            return await tools.ejecutar(p["herramienta"], p["args"], usuario["rol"], uid=usuario["id"])
    except ImportError:
        return await tools.ejecutar(p["herramienta"], p["args"], usuario["rol"], uid=usuario["id"])


# --- Generadores ----------------------------------------------------------------------------------------------------
def _ts(dt: datetime) -> float:
    return dt.timestamp()


async def _luz(u: dict, ahora: datetime) -> list:
    """Por la mañana: recordatorio para la hora más barata de la luz (si aún no ha pasado)."""
    from . import luz
    if not luz.activo() or not (8 <= ahora.hour < 13):
        return []
    r = await luz.hoy()
    h = r["barata"]["hora"]
    if h <= ahora.hour:
        return []
    cuando = ahora.replace(hour=h, minute=0, second=0, microsecond=0)
    precio = f"{r['barata']['precio']:.3f}".replace(".", ",")
    return [dict(clave=f"luz:{ahora.date().isoformat()}", tipo="luz",
                 titulo=f"¿Te aviso a las {h}:00 para poner la lavadora?",
                 detalle=f"Es la hora más barata de la luz hoy ({precio} €/kWh). Te pongo un recordatorio.",
                 herramienta="recordatorio",
                 args={"texto": "Poner la lavadora o el lavavajillas (hora más barata de la luz)", "cuando": cuando.strftime("%Y-%m-%dT%H:%M")},
                 caduca=_ts(cuando))]


def _citas(u: dict, ahora: datetime) -> list:
    """Cita con hora dentro de 45 min a 3 h: aviso 30 minutos antes."""
    from . import agenda
    eventos = agenda.listar_eventos(u["id"], ahora.date().isoformat(), (ahora.date() + timedelta(days=1)).isoformat())
    out = []
    for e in eventos:
        if e.get("todo_el_dia") or not e.get("inicio"):
            continue
        try:
            ini = datetime.fromisoformat(str(e["inicio"]))
            ini = ini.replace(tzinfo=ahora.tzinfo) if ini.tzinfo is None else ini.astimezone(ahora.tzinfo)
        except ValueError:
            continue
        falta = (ini - ahora).total_seconds()
        if not (45 * 60 <= falta <= 3 * 3600):
            continue
        aviso = ini - timedelta(minutes=30)
        lugar = f" en {e['lugar']}" if e.get("lugar") else ""
        out.append(dict(clave=f"cita:{e.get('id')}:{ini.isoformat()}", tipo="cita",
                        titulo=f"¿Te aviso a las {aviso:%H:%M} para salir hacia «{e['titulo']}»?",
                        detalle=f"Tienes «{e['titulo']}»{lugar} a las {ini:%H:%M}. Te recuerdo media hora antes.",
                        herramienta="recordatorio",
                        args={"texto": f"Salir hacia «{e['titulo']}» ({ini:%H:%M}{lugar})", "cuando": aviso.strftime("%Y-%m-%dT%H:%M")},
                        caduca=_ts(aviso)))
    return out


async def _red(u: dict, ahora: datetime) -> list:
    """Administradores: dispositivo nuevo y sin identificar (últimas 24 h): marcarlo como conocido."""
    from . import red
    if u["rol"] != "admin":
        return []
    out = []
    for d in await red.dispositivos():
        if d.get("conocido") or (d.get("primera_vez") or 0) < time.time() - 86400 or not d.get("ip"):
            continue
        nombre = d.get("nombre") or d.get("fabricante") or "sin nombre"
        out.append(dict(clave=f"red:{d.get('clave') or d['ip']}", tipo="red",
                        titulo=f"¿Es tuyo «{nombre}» ({d['ip']})?",
                        detalle="Ha entrado en la red en las últimas 24 horas y no está identificado. Si es de casa, lo marco como conocido "
                                "y dejo de avisarte. Si no lo reconoces, recházalo y míralo en Red.",
                        herramienta="marcar_dispositivo_conocido", args={"dispositivo": d["ip"]},
                        caduca=time.time() + 3 * 86400))
    return out


async def generar(ahora: datetime | None = None) -> list:
    """Crea las propuestas que tocan para cada usuario activo (no invitados). Devuelve las nuevas."""
    import asyncio
    from . import invitados, usuarios
    ahora = ahora or tiempo.ahora()
    nuevas = []
    for u in await asyncio.to_thread(usuarios.listar):
        if not u["activo"] or await asyncio.to_thread(invitados.de, u["id"]):
            continue
        candidatas = []
        for gen in (_luz, _red):
            try:
                candidatas += await gen(u, ahora)
            except Exception:  # noqa: BLE001 - una fuente caída no para a las demás
                log.exception("Falló el generador de propuestas %s", gen.__name__)
        try:
            candidatas += await asyncio.to_thread(_citas, u, ahora)
        except Exception:  # noqa: BLE001
            log.exception("Falló el generador de propuestas de citas")
        for c in candidatas:
            p = await asyncio.to_thread(crear, u["id"], **c)
            if p:
                nuevas.append((u, p))
    return nuevas


async def ciclo(ahora: datetime | None = None) -> int:
    """Una vuelta (la llama el planificador cada pocos minutos): caduca, genera y avisa por Telegram."""
    import asyncio
    await asyncio.to_thread(caducar)
    if not config.PROPUESTAS:
        return 0
    nuevas = await generar(ahora)
    if nuevas:
        from . import telegram
        for u, p in nuevas:
            try:
                await telegram.avisar_propuesta(u, p)
            except Exception:  # noqa: BLE001
                log.exception("No se pudo avisar de una propuesta por Telegram")
    return len(nuevas)
