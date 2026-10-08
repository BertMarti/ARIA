"""Recordatorios por usuario: «recuérdame mañana a las 9 llamar al taller».

El cerebro en la nube convierte el español natural en una fecha ISO (tiene la fecha y el día de la semana
en el prompt) y, si hace falta, una repetición sencilla (diario, semanal, laborables). Como red de
seguridad (cerebro local, o el modelo pasa la frase tal cual), `interpretar` entiende las formas más
habituales: «en 20 minutos», «mañana a las 9», «el viernes por la tarde», «todos los lunes a las 8».

El planificador de avisos los dispara por los canales del usuario (Telegram con botones +10 min / +1 h /
Hecho, push y la campana). Los recordatorios no respetan las horas de silencio: los pide el usuario.
"""
import asyncio
import re
import time
import unicodedata
from contextlib import closing
from datetime import date, datetime, time as hora, timedelta

from . import avisos, db, tiempo

MAX_TEXTO = 200
MAX_ACTIVOS = 100
REPETICIONES = ("diario", "semanal", "laborables")
NOMBRE_REPETIR = {"diario": "todos los días", "semanal": "cada semana", "laborables": "de lunes a viernes"}
POSPONER_MIN = (10, 60)


class RecordatorioError(Exception):
    """Error legible (en español)."""


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS recordatorios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                texto TEXT NOT NULL, cuando REAL NOT NULL, repetir TEXT,
                estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente','avisado','hecho')),
                creado REAL NOT NULL, avisado REAL);
            CREATE INDEX IF NOT EXISTS idx_record_pend ON recordatorios(estado, cuando);
            CREATE INDEX IF NOT EXISTS idx_record_user ON recordatorios(user_id, cuando);
        """)


# --- Interpretar fechas en español ------------------------------------------------------------------
_DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
_MESES = {m: i + 1 for i, m in enumerate(("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                          "septiembre", "octubre", "noviembre", "diciembre"))}
_NUM = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
        "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40,
        "cuarenta y cinco": 45}
_FRANJAS = {"manana": 9, "mediodia": 13, "tarde": 17, "noche": 21, "madrugada": 6}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[¿?¡!,;]", " ", t)).strip()


def _num(t: str) -> int | None:
    t = t.strip()
    if t.isdigit():
        return int(t)
    return _NUM.get(t)


def _local(d: date, h: int, m: int = 0) -> datetime:
    return datetime.combine(d, hora(h % 24, m), tzinfo=tiempo.zona())


def _iso(t: str) -> datetime | None:
    t = t.strip().replace(" ", "T", 1) if re.match(r"^\d{4}-\d{2}-\d{2} \d", t.strip()) else t.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}(T\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?)?([+-]\d{2}:?\d{2}|Z)?$", t):
        return None
    try:
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None
    if "T" not in t:
        d = datetime.combine(d.date(), hora(9, 0))  # solo fecha: a las 9 de la mañana
    return d.replace(tzinfo=tiempo.zona()) if d.tzinfo is None else d.astimezone(tiempo.zona())


def _hora_de(t: str) -> tuple | None:
    """(hora, minuto) de «a las 9», «a las 18:30», «a las 9 y media», «a las 9 de la noche», «a mediodía»."""
    if re.search(r"\b(a )?mediodia\b", t):
        return 13, 0
    if re.search(r"\b(a )?medianoche\b", t):
        return 0, 0
    m = re.search(r"\ba las? (\d{1,2}|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce)"
                  r"(?:[:.h](\d{2}))?(?: ?(y media|y cuarto|menos cuarto))?(?: ?(?:h|horas?))?"
                  r"(?: ?(de la manana|de la tarde|de la noche|de la madrugada|am|pm))?\b", t)
    if not m:
        m2 = re.search(r"\b(\d{1,2})[:.](\d{2})\b", t)
        if not m2:
            return None
        return int(m2.group(1)), int(m2.group(2))
    h, mi = _num(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == "y media":
        mi = 30
    elif m.group(3) == "y cuarto":
        mi = 15
    elif m.group(3) == "menos cuarto":
        h, mi = h - 1, 45
    suf = m.group(4) or ""
    if suf in ("de la tarde", "de la noche", "pm") and h < 12:
        h += 12
    if suf == "de la noche" and h == 24:
        h = 0
    if h > 23 or mi > 59:
        return None
    return h, mi


def interpretar(cuando: str, ref: datetime | None = None) -> tuple:
    """Devuelve (datetime local, repetir | None) o lanza RecordatorioError si no se entiende."""
    ref = (ref.astimezone(tiempo.zona()) if ref else tiempo.ahora()).replace(second=0, microsecond=0)
    bruto = str(cuando or "").strip()
    if not bruto:
        raise RecordatorioError("Dime cuándo quieres que te lo recuerde.")
    d = _iso(bruto)
    if d:
        return d, None
    t = _norm(bruto)

    # Repetición
    repetir = None
    if re.search(r"\b(todos los dias|cada dia|a diario|diariamente)\b", t):
        repetir = "diario"
    elif re.search(r"\b(entre semana|dias laborables|laborables|de lunes a viernes)\b", t):
        repetir = "laborables"
    elif re.search(r"\b(todos los|cada) (lunes|martes|miercoles|jueves|viernes|sabados?|domingos?)\b", t) \
            or re.search(r"\b(cada semana|semanalmente|todas las semanas)\b", t):
        repetir = "semanal"

    # Relativo: «en 20 minutos», «dentro de 2 horas», «en media hora»
    m = re.search(r"\b(?:en|dentro de) (media hora|un cuarto de hora|(\d+|[a-z]+(?: y [a-z]+)?) "
                  r"(minutos?|mins?|horas?|h|dias?|semanas?))\b", t)
    if m and not repetir:
        if m.group(1) == "media hora":
            return ref + timedelta(minutes=30), None
        if m.group(1) == "un cuarto de hora":
            return ref + timedelta(minutes=15), None
        n = _num(m.group(2))
        if n is None:
            raise RecordatorioError("No entiendo cuánto tiempo. Prueba con «en 20 minutos» o «mañana a las 9».")
        u = m.group(3)
        delta = (timedelta(minutes=n) if u.startswith("min") else timedelta(hours=n) if u.startswith("h")
                 else timedelta(days=n) if u.startswith("dia") else timedelta(weeks=n))
        return ref + delta, None

    hm = _hora_de(t)
    franja = next((f for f in ("madrugada", "mediodia", "tarde", "noche") if re.search(rf"\b(por la|esta|a la) {f}\b", t)), None)
    if franja is None and re.search(r"\b(por la|esta) manana\b", t):
        franja = "manana"
    if hm and franja in ("tarde", "noche") and hm[0] < 12:
        hm = (hm[0] + 12, hm[1])
    if not hm and franja:
        hm = (_FRANJAS[franja], 0)

    # Día
    dia = None
    explicito = False
    if re.search(r"\bpasado manana\b", t):
        dia, explicito = ref.date() + timedelta(days=2), True
    elif re.search(r"\bmanana\b", t) and not re.search(r"\b(por la|esta|de la) manana\b", t.replace("pasado manana", "")) \
            or re.search(r"\bmanana (por la|a las?|a medio)", t):
        dia, explicito = ref.date() + timedelta(days=1), True
    elif re.search(r"\b(hoy|esta (tarde|noche|manana))\b", t):
        dia, explicito = ref.date(), True
    md = re.search(r"\b(?:el )?(\d{1,2}) de (" + "|".join(_MESES) + r")(?: de (\d{4}))?\b", t)
    mn = re.search(r"\b(?:el|este|el proximo|proximo) (lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b", t) \
        or re.search(r"\b(?:todos los|cada) (lunes|martes|miercoles|jueves|viernes|sabado|domingo)s?\b", t)
    mdia = re.search(r"\bel (?:dia )?(\d{1,2})\b(?! de)", t)
    if md:
        anio = int(md.group(3) or ref.year)
        try:
            dia = date(anio, _MESES[md.group(2)], int(md.group(1)))
        except ValueError:
            raise RecordatorioError("Esa fecha no existe.") from None
        if dia < ref.date() and not md.group(3):
            dia = date(anio + 1, dia.month, dia.day)
        explicito = True
    elif mn:
        objetivo = _DIAS[mn.group(1)]
        dias = (objetivo - ref.weekday()) % 7
        dia, explicito = ref.date() + timedelta(days=dias), True
        if dias == 0 and hm and _local(dia, *hm) <= ref:
            dia += timedelta(days=7)
    elif mdia and not hm or (mdia and hm and not re.search(r"\ba las? " + mdia.group(1), t)):
        n = int(mdia.group(1))
        if 1 <= n <= 31:
            y, mo = ref.year, ref.month
            if n < ref.day:
                y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
            try:
                dia, explicito = date(y, mo, n), True
            except ValueError:
                raise RecordatorioError("Ese día no existe en ese mes.") from None

    if dia is None and hm is None:
        if repetir:
            hm = (9, 0)
        else:
            raise RecordatorioError("No entiendo cuándo. Prueba con «mañana a las 9», «en 20 minutos» o "
                                    "«el viernes a las 18:00».")
    if hm is None:
        hm = (9, 0)
    if dia is None:
        dia = ref.date()
    resultado = _local(dia, *hm)
    if resultado <= ref:
        if not explicito or repetir:
            # «a las 9» sin día: la próxima vez que sean las 9 (o las 21, si las 9 ya pasaron y es ambiguo)
            if not explicito and hm[0] < 12 and not re.search(r"de la manana|\bam\b", t) and _local(dia, hm[0] + 12, hm[1]) > ref \
                    and not franja and not repetir:
                resultado = _local(dia, hm[0] + 12, hm[1])
            else:
                resultado = _local(dia + timedelta(days=1), *hm)
                while repetir == "laborables" and resultado.weekday() > 4:
                    resultado = _local(resultado.date() + timedelta(days=1), *hm)
        elif dia == ref.date() and hm[0] < 12 and _local(dia, hm[0] + 12, hm[1]) > ref and not franja \
                and not re.search(r"de la manana|\bam\b", t):
            resultado = _local(dia, hm[0] + 12, hm[1])  # «hoy a las 5» a las 10:00 -> 17:00
    if repetir == "laborables":
        while resultado.weekday() > 4:
            resultado = _local(resultado.date() + timedelta(days=1), *hm)
    return resultado, repetir


def siguiente(cuando: datetime, repetir: str, ref: datetime) -> datetime:
    """Próxima repetición estrictamente posterior a `ref` (a la misma hora local, aunque cambie la hora oficial)."""
    cuando = cuando.astimezone(tiempo.zona())
    h, m = cuando.hour, cuando.minute
    paso = 7 if repetir == "semanal" else 1
    d = cuando.date()
    while True:
        d += timedelta(days=paso)
        if repetir == "laborables" and d.weekday() > 4:
            continue
        nuevo = _local(d, h, m)
        if nuevo > ref:
            return nuevo


def describir(cuando: float, repetir: str | None = None, ref: datetime | None = None) -> str:
    ref = (ref.astimezone(tiempo.zona()) if ref else tiempo.ahora())
    d = datetime.fromtimestamp(cuando, tiempo.zona())
    hm = f"{d:%H:%M}"
    if repetir:
        if repetir == "semanal":
            return f"cada {tiempo.DIAS[d.weekday()]} a las {hm}"
        return f"{NOMBRE_REPETIR[repetir]} a las {hm}"
    dias = (d.date() - ref.date()).days
    if dias == 0:
        return f"hoy a las {hm}"
    if dias == 1:
        return f"mañana a las {hm}"
    if 1 < dias < 7:
        return f"el {tiempo.DIAS[d.weekday()]} a las {hm}"
    return f"el {tiempo.DIAS[d.weekday()]} {d.day} de {tiempo.MESES[d.month - 1]} a las {hm}"


# --- CRUD ----------------------------------------------------------------------------------------------
def _fila(r, ref: datetime | None = None) -> dict:
    return {"id": r["id"], "texto": r["texto"], "cuando": r["cuando"], "repetir": r["repetir"],
            "estado": r["estado"], "descripcion": describir(r["cuando"], r["repetir"], ref)}


def limpiar_texto(texto) -> str:
    t = " ".join(str(texto or "").split())
    t = re.sub(r"^(que |de |el |la )", "", t, flags=re.I).strip()
    if not t:
        raise RecordatorioError("¿Qué quieres que te recuerde?")
    return t[:MAX_TEXTO]


def crear(uid: int, texto, cuando, repetir=None, ref: datetime | None = None) -> dict:
    """`cuando`: ISO local («2026-10-09T09:00») o una frase («mañana a las 9»). `repetir`: diario|semanal|laborables."""
    ref = (ref.astimezone(tiempo.zona()) if ref else tiempo.ahora())
    t = limpiar_texto(texto)
    rep_txt = _norm(repetir or "")
    rep = {"diario": "diario", "diaria": "diario", "daily": "diario", "semanal": "semanal", "weekly": "semanal",
           "laborables": "laborables", "": None, "no": None, "ninguna": None, "nunca": None}.get(rep_txt, "?")
    if rep == "?":
        raise RecordatorioError("La repetición debe ser diario, semanal o laborables.")
    momento, rep2 = interpretar(cuando, ref)
    rep = rep or rep2
    if not rep and momento < ref - timedelta(minutes=1):
        raise RecordatorioError("Esa hora ya ha pasado. Dime otra.")
    if momento > ref + timedelta(days=3 * 366):
        raise RecordatorioError("Es demasiado lejos (como mucho, tres años).")
    if rep and momento <= ref:
        momento = siguiente(momento, rep, ref)
    with closing(db._con()) as con, con:
        if con.execute("SELECT COUNT(*) FROM recordatorios WHERE user_id=? AND estado='pendiente'", (uid,)).fetchone()[0] >= MAX_ACTIVOS:
            raise RecordatorioError(f"Ya tienes {MAX_ACTIVOS} recordatorios pendientes; borra alguno.")
        rid = con.execute("INSERT INTO recordatorios (user_id, texto, cuando, repetir, creado) VALUES (?,?,?,?,?)",
                          (uid, t, momento.timestamp(), rep, time.time())).lastrowid
        r = con.execute("SELECT * FROM recordatorios WHERE id=?", (rid,)).fetchone()
    return _fila(r, ref)


def listar(uid: int, ref: datetime | None = None) -> list:
    with closing(db._con()) as con:
        return [_fila(r, ref) for r in con.execute(
            "SELECT * FROM recordatorios WHERE user_id=? AND estado='pendiente' ORDER BY cuando LIMIT 200", (uid,))]


def obtener(uid: int, rid: int) -> dict | None:
    with closing(db._con()) as con:
        r = con.execute("SELECT * FROM recordatorios WHERE id=? AND user_id=?", (rid, uid)).fetchone()
    return _fila(r) if r else None


def borrar(uid: int, rid: int) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM recordatorios WHERE id=? AND user_id=?", (rid, uid)).rowcount > 0


def buscar(uid: int, consulta) -> list:
    q = str(consulta or "").strip().lstrip("#")
    if q.isdigit():
        r = obtener(uid, int(q))
        return [r] if r and r["estado"] == "pendiente" else []
    palabras = [p for p in _norm(q).split() if len(p) > 2]
    return [r for r in listar(uid) if palabras and all(p in _norm(r["texto"]) for p in palabras)]


def posponer(uid: int, rid: int, minutos: int) -> dict | None:
    """Pospone un recordatorio. Si se repite, se crea uno puntual (la serie sigue igual)."""
    with closing(db._con()) as con, con:
        r = con.execute("SELECT * FROM recordatorios WHERE id=? AND user_id=?", (rid, uid)).fetchone()
        if not r:
            return None
        nuevo = time.time() + max(1, min(int(minutos), 24 * 60)) * 60
        if r["repetir"]:
            nid = con.execute("INSERT INTO recordatorios (user_id, texto, cuando, creado) VALUES (?,?,?,?)",
                              (uid, r["texto"], nuevo, time.time())).lastrowid
        else:
            nid = rid
            con.execute("UPDATE recordatorios SET cuando=?, estado='pendiente' WHERE id=?", (nuevo, rid))
        return _fila(con.execute("SELECT * FROM recordatorios WHERE id=?", (nid,)).fetchone())


def hecho(uid: int, rid: int) -> bool:
    with closing(db._con()) as con, con:
        r = con.execute("SELECT repetir FROM recordatorios WHERE id=? AND user_id=?", (rid, uid)).fetchone()
        if not r:
            return False
        if not r["repetir"]:
            con.execute("UPDATE recordatorios SET estado='hecho' WHERE id=?", (rid,))
        return True


def vencidos(ahora: float) -> list:
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM recordatorios WHERE estado='pendiente' AND cuando<=? ORDER BY cuando LIMIT 50", (ahora,))]


def _avanzar(r: dict, ahora: float) -> None:
    with closing(db._con()) as con, con:
        if r["repetir"]:
            prox = siguiente(datetime.fromtimestamp(r["cuando"], tiempo.zona()), r["repetir"],
                             datetime.fromtimestamp(ahora, tiempo.zona()))
            con.execute("UPDATE recordatorios SET cuando=?, avisado=? WHERE id=?", (prox.timestamp(), ahora, r["id"]))
        else:
            con.execute("UPDATE recordatorios SET estado='avisado', avisado=? WHERE id=?", (ahora, r["id"]))
        con.execute("DELETE FROM recordatorios WHERE estado IN ('avisado','hecho') AND cuando<?", (ahora - 30 * 86400,))


async def disparar_vencidos(ahora: float | None = None) -> list:
    """Lo llama el planificador: avisa de los recordatorios vencidos y programa la siguiente repetición."""
    ahora = time.time() if ahora is None else ahora
    hechos = []
    for r in await asyncio.to_thread(vencidos, ahora):
        await asyncio.to_thread(_avanzar, r, ahora)  # primero: si la entrega falla, no se repite en bucle
        retraso = ahora - r["cuando"]
        texto = f"Recordatorio: {r['texto']}" + (" (con retraso: ARIA estaba apagada)" if retraso > 3600 else "")
        await avisos.emitir("recordatorio", "aviso", texto, "ajustes", [r["user_id"]], ignorar_silencio=True,
                            extra={"recordatorio": r["id"], "repetir": r["repetir"]})
        hechos.append(r["id"])
    return hechos
