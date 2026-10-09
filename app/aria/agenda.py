"""Agenda personal y cumpleaños, siempre aislados por usuario."""
import calendar
import hashlib
import re
import secrets
import time
from contextlib import closing
from datetime import date, datetime, time as hora, timedelta, timezone

from . import db, tiempo

MAX_TITULO, MAX_LUGAR, MAX_NOTAS, MAX_NOMBRE = 160, 160, 2000, 120
REPETICIONES = ("ninguna", "semanal", "mensual", "anual")


class AgendaError(Exception):
    """Error de validación legible para la API y el chat."""


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS agenda_eventos (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
          titulo TEXT NOT NULL, inicio TEXT NOT NULL, fin TEXT, todo_el_dia INTEGER NOT NULL DEFAULT 0,
          lugar TEXT NOT NULL DEFAULT '', notas TEXT NOT NULL DEFAULT '', repeticion TEXT NOT NULL DEFAULT 'ninguna',
          aviso_min INTEGER, creado REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_agenda_eventos_user ON agenda_eventos(user_id, inicio);
        CREATE TABLE IF NOT EXISTS agenda_cumpleanos (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
          nombre TEXT NOT NULL, dia INTEGER NOT NULL, mes INTEGER NOT NULL, anio INTEGER, aviso_dias INTEGER NOT NULL DEFAULT 0,
          notas TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS idx_agenda_cumple_user ON agenda_cumpleanos(user_id, mes, dia);
        CREATE TABLE IF NOT EXISTS agenda_suscripcion (
          user_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE, token_hash TEXT NOT NULL UNIQUE,
          creado REAL NOT NULL);
        """)


def _texto(v, maximo, campo, obligatorio=False):
    s = " ".join(str(v or "").split())
    if obligatorio and not s:
        raise AgendaError(f"Indica {campo}.")
    if len(s) > maximo:
        raise AgendaError(f"{campo.capitalize()} no puede superar {maximo} caracteres.")
    return s


def _fecha(v, campo="la fecha") -> datetime:
    s = str(v or "").strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        raise AgendaError(f"{campo.capitalize()} no es válida; usa AAAA-MM-DD o AAAA-MM-DDTHH:MM.") from None
    if d.tzinfo is None:
        return d.replace(tzinfo=tiempo.zona())
    return d.astimezone(tiempo.zona())


def _iso(d):
    return d.astimezone(tiempo.zona()).replace(second=0, microsecond=0).isoformat(timespec="minutes")


def _evento(r):
    d = dict(r)
    d["todo_el_dia"] = bool(d["todo_el_dia"])
    d["aviso_min"] = None if d["aviso_min"] is None else int(d["aviso_min"])
    return d


def _datos_evento(datos, existente=None):
    d = dict(existente or {})
    d.update({k: v for k, v in (datos or {}).items() if k in
              {"titulo", "inicio", "fin", "todo_el_dia", "lugar", "notas", "repeticion", "aviso_min"}})
    d["titulo"] = _texto(d.get("titulo"), MAX_TITULO, "el título", True)
    d["inicio"] = _iso(_fecha(d.get("inicio"), "el inicio"))
    if d.get("fin"):
        d["fin"] = _iso(_fecha(d["fin"], "el final"))
        if d["fin"] <= d["inicio"]:
            raise AgendaError("El final debe ser posterior al inicio.")
    else:
        d["fin"] = None
    d["todo_el_dia"] = bool(d.get("todo_el_dia", False))
    d["lugar"] = _texto(d.get("lugar"), MAX_LUGAR, "el lugar")
    d["notas"] = _texto(d.get("notas"), MAX_NOTAS, "las notas")
    d["repeticion"] = str(d.get("repeticion") or "ninguna").lower()
    if d["repeticion"] not in REPETICIONES:
        raise AgendaError("La repetición debe ser ninguna, semanal, mensual o anual.")
    if d.get("aviso_min") in (None, ""):
        d["aviso_min"] = None
    else:
        try: d["aviso_min"] = int(d["aviso_min"])
        except (TypeError, ValueError): raise AgendaError("El aviso debe ser un número de minutos.") from None
        if not 0 <= d["aviso_min"] <= 10080:
            raise AgendaError("El aviso debe estar entre 0 y 10080 minutos.")
    return d


def crear_evento(uid, datos):
    d = _datos_evento(datos)
    with closing(db._con()) as con, con:
        eid = con.execute("INSERT INTO agenda_eventos (user_id,titulo,inicio,fin,todo_el_dia,lugar,notas,repeticion,aviso_min,creado) VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (uid, d["titulo"], d["inicio"], d["fin"], int(d["todo_el_dia"]), d["lugar"], d["notas"], d["repeticion"], d["aviso_min"], time.time())).lastrowid
        return _evento(con.execute("SELECT * FROM agenda_eventos WHERE id=?", (eid,)).fetchone())


def editar_evento(uid, eid, datos):
    with closing(db._con()) as con, con:
        r = con.execute("SELECT * FROM agenda_eventos WHERE id=? AND user_id=?", (eid, uid)).fetchone()
        if not r: return None
        d = _datos_evento(datos, dict(r))
        con.execute("UPDATE agenda_eventos SET titulo=?,inicio=?,fin=?,todo_el_dia=?,lugar=?,notas=?,repeticion=?,aviso_min=? WHERE id=? AND user_id=?",
                    (d["titulo"],d["inicio"],d["fin"],int(d["todo_el_dia"]),d["lugar"],d["notas"],d["repeticion"],d["aviso_min"],eid,uid))
        return _evento(con.execute("SELECT * FROM agenda_eventos WHERE id=?", (eid,)).fetchone())


def borrar_evento(uid, eid):
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM agenda_eventos WHERE id=? AND user_id=?", (eid, uid)).rowcount > 0


def _suma(d, rep, n=1):
    if rep == "semanal": return d + timedelta(days=7*n)
    if rep == "mensual":
        i = d.year * 12 + d.month - 1 + n
        y, m = divmod(i, 12); return d.replace(year=y, month=m+1, day=min(d.day, calendar.monthrange(y,m+1)[1]))
    if rep == "anual":
        try: return d.replace(year=d.year+n)
        except ValueError: return d.replace(year=d.year+n, day=28)
    return d


def _primer_paso(base, ini, rep):
    """Primer índice de repetición que puede caer en el rango (evita recorrer años de historia paso a paso)."""
    if ini <= base:
        return 0
    if rep == "semanal":
        return max(0, (ini - base).days // 7 - 1)
    if rep == "mensual":
        return max(0, (ini.year - base.year) * 12 + ini.month - base.month - 1)
    if rep == "anual":
        return max(0, ini.year - base.year - 1)
    return 0


def _ocurrencias(r, desde, hasta):
    ini, fin = _fecha(desde, "desde"), _fecha(hasta, "hasta")
    base = _fecha(r["inicio"], "el inicio")
    final = _fecha(r["fin"], "el final") if r.get("fin") else None
    duracion = (final - base) if final and final > base else None   # cada repetición dura lo mismo
    if r["repeticion"] == "ninguna":
        candidatos = [base]
    else:
        candidatos, n = [], _primer_paso(base, ini, r["repeticion"])
        for _ in range(500):
            x = _suma(base, r["repeticion"], n)
            if x >= fin:
                break
            if x >= ini:
                candidatos.append(x)
            n += 1
        else:
            raise AgendaError("El rango solicitado es demasiado grande.")
    out = []
    for x in candidatos:
        if x < ini or x >= fin:
            continue
        y = dict(r)
        y["inicio"] = _iso(x)
        if duracion is not None:
            y["fin"] = _iso(x + duracion)
        y["ocurrencia"] = _iso(x)
        y["serie_inicio"] = r["inicio"]   # para editar una serie desde cualquiera de sus repeticiones
        out.append(_evento(y))
    return out


def listar_eventos(uid, desde, hasta):
    ini, fin = _fecha(desde, "desde"), _fecha(hasta, "hasta")
    if fin <= ini or fin - ini > timedelta(days=366): raise AgendaError("El rango debe ser válido y no superar un año.")
    with closing(db._con()) as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM agenda_eventos WHERE user_id=? AND inicio<? ORDER BY inicio", (uid, _iso(fin)))]
    return [x for r in rows for x in _ocurrencias(r, _iso(ini), _iso(fin))]


def _cumple(r, year):
    day = min(r["dia"], calendar.monthrange(year, r["mes"])[1])
    return date(year, r["mes"], day)


def _cumple_fila(r, ref):
    d = _cumple(r, ref.year)
    if d < ref.date(): d = _cumple(r, ref.year + 1)
    edad = d.year - r["anio"] if r.get("anio") else None
    return {**dict(r), "fecha": d.isoformat(), "edad": edad}


def _datos_cumple(datos, existente=None):
    d = dict(existente or {}); d.update({k:v for k,v in (datos or {}).items() if k in {"nombre","dia","mes","anio","aviso_dias","notas"}})
    d["nombre"] = _texto(d.get("nombre"), MAX_NOMBRE, "el nombre", True)
    try: d["dia"], d["mes"] = int(d["dia"]), int(d["mes"])
    except (TypeError, ValueError): raise AgendaError("El día y el mes deben ser números.") from None
    if not 1 <= d["mes"] <= 12 or not 1 <= d["dia"] <= calendar.monthrange(2024 if d["mes"]==2 and d["dia"]==29 else 2023,d["mes"])[1]: raise AgendaError("Ese día y mes no existen.")
    if d.get("anio") not in (None, ""):
        try: d["anio"] = int(d["anio"])
        except (TypeError, ValueError): raise AgendaError("El año debe ser un número.") from None
        if d["anio"] < 1 or d["anio"] > tiempo.ahora().year: raise AgendaError("El año de nacimiento no es válido.")
    else: d["anio"] = None
    try: d["aviso_dias"] = max(0, min(365, int(d.get("aviso_dias", 0))))
    except (TypeError, ValueError): raise AgendaError("El aviso debe ser un número de días.") from None
    d["notas"] = _texto(d.get("notas"), MAX_NOTAS, "las notas")
    return d


def listar_cumpleanos(uid, dias=30, ref=None):
    ref = (ref or tiempo.ahora()).astimezone(tiempo.zona()); dias=max(0,min(366,int(dias)))
    with closing(db._con()) as con: rows=[dict(r) for r in con.execute("SELECT * FROM agenda_cumpleanos WHERE user_id=? ORDER BY mes,dia,nombre",(uid,))]
    return [x for r in rows for x in [_cumple_fila(r,ref)] if date.fromisoformat(x["fecha"]) <= ref.date()+timedelta(days=dias)]


def crear_cumple(uid, datos):
    d=_datos_cumple(datos)
    with closing(db._con()) as con, con:
        cid=con.execute("INSERT INTO agenda_cumpleanos (user_id,nombre,dia,mes,anio,aviso_dias,notas) VALUES (?,?,?,?,?,?,?)",(uid,d["nombre"],d["dia"],d["mes"],d["anio"],d["aviso_dias"],d["notas"])).lastrowid
    return {**d,"id":cid}


def editar_cumple(uid,cid,datos):
    with closing(db._con()) as con, con:
        r=con.execute("SELECT * FROM agenda_cumpleanos WHERE id=? AND user_id=?",(cid,uid)).fetchone()
        if not r:return None
        d=_datos_cumple(datos,dict(r)); con.execute("UPDATE agenda_cumpleanos SET nombre=?,dia=?,mes=?,anio=?,aviso_dias=?,notas=? WHERE id=? AND user_id=?",(d["nombre"],d["dia"],d["mes"],d["anio"],d["aviso_dias"],d["notas"],cid,uid)); return {**d,"id":cid}


def borrar_cumple(uid,cid):
    with closing(db._con()) as con, con:return con.execute("DELETE FROM agenda_cumpleanos WHERE id=? AND user_id=?",(cid,uid)).rowcount>0


def _debe(clave):
    with closing(db._con()) as con, con:
        if con.execute("SELECT 1 FROM avisos_estado WHERE clave=?",(clave,)).fetchone(): return False
        con.execute("INSERT INTO avisos_estado (clave,chequeo,activo,desde) VALUES (?,?,0,?)",(clave,"agenda",time.time())); return True


async def disparar_avisos(ahora=None):
    from . import avisos, usuarios
    ref=datetime.fromtimestamp(ahora or time.time(),tiempo.zona()).replace(second=0,microsecond=0); hechos=[]
    for u in await __import__('asyncio').to_thread(usuarios.listar):
        uid=u["id"]
        eventos=await __import__('asyncio').to_thread(listar_eventos,uid,_iso(ref-timedelta(days=1)),_iso(ref+timedelta(days=1)))
        for e in eventos:
            if e["aviso_min"] is None: continue
            objetivo=_fecha(e["inicio"])-timedelta(minutes=e["aviso_min"])
            if objetivo <= ref and await __import__('asyncio').to_thread(_debe,f"agenda:evento:{e['id']}:{e['ocurrencia']}"):
                await avisos.emitir("agenda","aviso",f"Agenda: {e['titulo']} empieza {('hoy' if e['todo_el_dia'] else 'a las '+_fecha(e['inicio']).strftime('%H:%M'))}.","agenda",[uid],extra={"evento":e["id"]}); hechos.append(e["id"])
        for c in await __import__('asyncio').to_thread(listar_cumpleanos,uid,366,ref):
            d=date.fromisoformat(c["fecha"])-timedelta(days=c["aviso_dias"])
            if d == ref.date() and 9 <= ref.hour < 10 and await __import__('asyncio').to_thread(_debe,f"agenda:cumple:{c['id']}:{d.isoformat()}"):
                edad=f"; cumple {c['edad']} años" if c.get("edad") is not None else ""
                await avisos.emitir("agenda","info",f"Cumpleaños: {c['nombre']}{edad}.","agenda",[uid],extra={"cumpleanos":c["id"]}); hechos.append(c["id"])
    return hechos


# --- Exportar a otros calendarios (iCalendar, RFC 5545) ------------------------------------------------------------
_RRULE = {"semanal": "FREQ=WEEKLY", "mensual": "FREQ=MONTHLY", "anual": "FREQ=YEARLY"}


def _ics_texto(v) -> str:
    return str(v or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _plegar(linea: str) -> str:
    """Líneas de 75 octetos como máximo; las continuaciones empiezan por un espacio."""
    b = linea.encode()
    if len(b) <= 75:
        return linea
    trozos, actual = [], b""
    for ch in linea:
        c = ch.encode()
        if len(actual) + len(c) > (75 if not trozos else 74):
            trozos.append(actual.decode()); actual = b""
        actual += c
    trozos.append(actual.decode())
    return "\r\n ".join(trozos)


def _utc(iso: str) -> str:
    return _fecha(iso).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ics(uid: int) -> str:
    """Calendario completo del usuario: eventos (con su repetición) y cumpleaños (cada año, todo el día)."""
    sello = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lineas = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//ARIA//Agenda//ES", "CALSCALE:GREGORIAN",
              "X-WR-CALNAME:ARIA", "X-PUBLISHED-TTL:PT1H", "REFRESH-INTERVAL;VALUE=DURATION:PT1H"]
    with closing(db._con()) as con:
        eventos = [dict(r) for r in con.execute("SELECT * FROM agenda_eventos WHERE user_id=? ORDER BY inicio", (uid,))]
        cumples = [dict(r) for r in con.execute("SELECT * FROM agenda_cumpleanos WHERE user_id=?", (uid,))]
    for e in eventos:
        lineas += ["BEGIN:VEVENT", f"UID:evento-{e['id']}@aria", f"DTSTAMP:{sello}", f"SUMMARY:{_ics_texto(e['titulo'])}"]
        if e["todo_el_dia"]:
            d = _fecha(e["inicio"]).date()
            lineas += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}"]
        else:
            lineas.append(f"DTSTART:{_utc(e['inicio'])}")
            lineas.append(f"DTEND:{_utc(e['fin'])}" if e.get("fin") else "DURATION:PT1H")
        if e["repeticion"] in _RRULE:
            lineas.append("RRULE:" + _RRULE[e["repeticion"]])
        if e.get("lugar"):
            lineas.append(f"LOCATION:{_ics_texto(e['lugar'])}")
        if e.get("notas"):
            lineas.append(f"DESCRIPTION:{_ics_texto(e['notas'])}")
        if e.get("aviso_min") is not None:
            lineas += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_texto(e['titulo'])}",
                       f"TRIGGER:-PT{int(e['aviso_min'])}M", "END:VALARM"]
        lineas.append("END:VEVENT")
    for c in cumples:
        anio = c["anio"] or 2000
        dia = min(c["dia"], calendar.monthrange(anio, c["mes"])[1])
        inicio = date(anio, c["mes"], dia)
        lineas += ["BEGIN:VEVENT", f"UID:cumple-{c['id']}@aria", f"DTSTAMP:{sello}",
                   f"SUMMARY:{_ics_texto('Cumpleaños de ' + c['nombre'])}", f"DTSTART;VALUE=DATE:{inicio:%Y%m%d}",
                   f"DTEND;VALUE=DATE:{inicio + timedelta(days=1):%Y%m%d}", "RRULE:FREQ=YEARLY", "TRANSP:TRANSPARENT", "END:VEVENT"]
    lineas.append("END:VCALENDAR")
    return "\r\n".join(_plegar(x) for x in lineas) + "\r\n"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_suscripcion(uid: int) -> str:
    """Token nuevo (el anterior deja de valer). Solo se guarda su huella."""
    token = secrets.token_urlsafe(32)
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO agenda_suscripcion (user_id, token_hash, creado) VALUES (?,?,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET token_hash=excluded.token_hash, creado=excluded.creado",
                    (uid, _hash(token), time.time()))
    return token


def tiene_suscripcion(uid: int) -> bool:
    with closing(db._con()) as con:
        return con.execute("SELECT 1 FROM agenda_suscripcion WHERE user_id=?", (uid,)).fetchone() is not None


def borrar_suscripcion(uid: int) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM agenda_suscripcion WHERE user_id=?", (uid,)).rowcount > 0


def usuario_de_token(token: str) -> int | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{30,100}", token or ""):
        return None
    with closing(db._con()) as con:
        r = con.execute("SELECT s.user_id FROM agenda_suscripcion s JOIN usuarios u ON u.id=s.user_id "
                        "WHERE s.token_hash=? AND u.activo=1", (_hash(token),)).fetchone()
    return r["user_id"] if r else None
