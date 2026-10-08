"""Automatizaciones: reglas de evento, horario o umbral para cada administrador.

Las acciones se ejecutan fuera del contexto de avisos y llevan una marca de origen para
que una acción que emita otro aviso no pueda iniciar una cascada.
"""
import asyncio
import json
import logging
import operator
import time
from contextlib import closing
from datetime import datetime

from . import avisos, db, tiempo

log = logging.getLogger("aria.automatizaciones")
MAX_POR_USUARIO = 20
ANTI_BUCLE_S = 5 * 60
MAX_REGISTRO = 200
ACCIONES = {"avisar", "pausar_internet_dispositivo", "pausar_bloqueador", "reanudar_bloqueador",
            "ejecutar_rutina", "escanear_red"}
_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "=": operator.eq}


class AutomatizacionError(Exception):
    pass


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS automatizaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL, activa INTEGER NOT NULL DEFAULT 1,
                disparador TEXT NOT NULL, condiciones TEXT NOT NULL DEFAULT '{}',
                acciones TEXT NOT NULL, creado REAL NOT NULL, ultimo_disparo REAL);
            CREATE INDEX IF NOT EXISTS idx_auto_user ON automatizaciones(user_id);
            CREATE TABLE IF NOT EXISTS automatizaciones_registro (
                id INTEGER PRIMARY KEY AUTOINCREMENT, automatizacion_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                ts REAL NOT NULL, disparo TEXT NOT NULL, acciones TEXT NOT NULL, resultado TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_auto_reg ON automatizaciones_registro(user_id, ts DESC);
        """)


def _texto(v, maximo, campo):
    v = " ".join(str(v or "").split())
    if not v or len(v) > maximo:
        raise AutomatizacionError(f"{campo} no válido.")
    return v


def _validar_disparador(d):
    if not isinstance(d, dict) or d.get("tipo") not in {"aviso", "hora", "umbral"}:
        raise AutomatizacionError("El disparador debe ser aviso, hora o umbral.")
    tipo = d["tipo"]
    if tipo == "aviso":
        if d.get("aviso") not in avisos.TIPOS:
            raise AutomatizacionError("Tipo de aviso no válido.")
        return {"tipo": tipo, "aviso": d["aviso"]}
    if tipo == "hora":
        h = d.get("hora")
        if not isinstance(h, str) or len(h) != 5 or h[2] != ":":
            raise AutomatizacionError("La hora debe tener formato HH:MM.")
        try:
            if not (0 <= int(h[:2]) < 24 and 0 <= int(h[3:]) < 60): raise ValueError
        except ValueError:
            raise AutomatizacionError("La hora no es válida.") from None
        dias = d.get("dias", [])
        if not isinstance(dias, list) or not all(isinstance(x, int) and 0 <= x <= 6 for x in dias):
            raise AutomatizacionError("Los días no son válidos.")
        return {"tipo": tipo, "hora": h, "dias": sorted(set(dias))}
    if d.get("metrica") not in {"temperatura", "cpu"} or d.get("operador") not in _OPS:
        raise AutomatizacionError("Umbral no válido.")
    try: valor = float(d["valor"])
    except (KeyError, TypeError, ValueError): raise AutomatizacionError("El valor del umbral no es válido.") from None
    return {"tipo": tipo, "metrica": d["metrica"], "operador": d["operador"], "valor": valor}


def _validar_condiciones(c):
    if c is None: return {}
    if not isinstance(c, dict): raise AutomatizacionError("Las condiciones no son válidas.")
    out = {}
    if "desde" in c or "hasta" in c:
        out["desde"], out["hasta"] = c.get("desde", "00:00"), c.get("hasta", "23:59")
        for h in (out["desde"], out["hasta"]):
            if not isinstance(h, str) or avisos._hhmm(h, "") != h: raise AutomatizacionError("Franja horaria no válida.")
    if "dias" in c:
        if not isinstance(c["dias"], list) or not all(isinstance(x, int) and 0 <= x <= 6 for x in c["dias"]):
            raise AutomatizacionError("Días no válidos.")
        out["dias"] = sorted(set(c["dias"]))
    if "dispositivo_desconocido" in c:
        if not isinstance(c["dispositivo_desconocido"], bool): raise AutomatizacionError("Condición no válida.")
        out["dispositivo_desconocido"] = c["dispositivo_desconocido"]
    return out


def _validar_acciones(items):
    if not isinstance(items, list) or not items or len(items) > 10: raise AutomatizacionError("Acciones no válidas.")
    out = []
    for a in items:
        if not isinstance(a, dict) or a.get("tipo") not in ACCIONES: raise AutomatizacionError("Acción no permitida.")
        x = dict(a)
        tipo = x["tipo"]
        if tipo == "avisar": x["texto"] = _texto(x.get("texto"), 600, "Texto del aviso")
        elif tipo == "pausar_internet_dispositivo":
            if "minutos" in x and (not isinstance(x["minutos"], int) or not 1 <= x["minutos"] <= 7 * 24 * 60):
                raise AutomatizacionError("Minutos de pausa no válidos.")
        elif tipo == "pausar_bloqueador":
            if not isinstance(x.get("minutos"), int) or not 1 <= x["minutos"] <= 120: raise AutomatizacionError("Minutos no válidos.")
        elif tipo == "ejecutar_rutina":
            if not isinstance(x.get("rutina_id"), int): raise AutomatizacionError("Rutina no válida.")
        elif tipo == "escanear_red":
            if x.get("perfil", "rapido") not in {"rapido", "completo"}: raise AutomatizacionError("Perfil no válido.")
        out.append(x)
    return out


def _fila(r):
    return {"id": r["id"], "user_id": r["user_id"], "nombre": r["nombre"], "activa": bool(r["activa"]),
            "disparador": json.loads(r["disparador"]), "condiciones": json.loads(r["condiciones"]),
            "acciones": json.loads(r["acciones"]), "creado": r["creado"], "ultimo_disparo": r["ultimo_disparo"]}


def crear(uid, datos):
    if not isinstance(datos, dict): raise AutomatizacionError("Datos no válidos.")
    d, c, a = _validar_disparador(datos.get("disparador")), _validar_condiciones(datos.get("condiciones")), _validar_acciones(datos.get("acciones"))
    with closing(db._con()) as con, con:
        if con.execute("SELECT COUNT(*) FROM automatizaciones WHERE user_id=?", (uid,)).fetchone()[0] >= MAX_POR_USUARIO:
            raise AutomatizacionError(f"No puedes tener más de {MAX_POR_USUARIO} automatizaciones.")
        aid = con.execute("INSERT INTO automatizaciones(user_id,nombre,disparador,condiciones,acciones,creado) VALUES(?,?,?,?,?,?)",
                          (uid, _texto(datos.get("nombre"), 80, "Nombre"), json.dumps(d), json.dumps(c), json.dumps(a), time.time())).lastrowid
    return obtener(uid, aid)


def listar(uid):
    with closing(db._con()) as con: return [_fila(r) for r in con.execute("SELECT * FROM automatizaciones WHERE user_id=? ORDER BY id", (uid,))]


def obtener(uid, aid):
    with closing(db._con()) as con: r = con.execute("SELECT * FROM automatizaciones WHERE id=? AND user_id=?", (aid, uid)).fetchone()
    return _fila(r) if r else None


def actualizar(uid, aid, datos):
    actual = obtener(uid, aid)
    if not actual: return None
    if not isinstance(datos, dict): raise AutomatizacionError("Datos no válidos.")
    vals = {"nombre": _texto(datos.get("nombre", actual["nombre"]), 80, "Nombre"), "activa": int(datos.get("activa", actual["activa"]))}
    if not isinstance(datos.get("activa", actual["activa"]), (bool, int)): raise AutomatizacionError("«activa» no es válida.")
    if "disparador" in datos: vals["disparador"] = json.dumps(_validar_disparador(datos["disparador"]))
    if "condiciones" in datos: vals["condiciones"] = json.dumps(_validar_condiciones(datos["condiciones"]))
    if "acciones" in datos: vals["acciones"] = json.dumps(_validar_acciones(datos["acciones"]))
    with closing(db._con()) as con, con: con.execute("UPDATE automatizaciones SET " + ",".join(f"{k}=?" for k in vals) + " WHERE id=? AND user_id=?", (*vals.values(), aid, uid))
    return obtener(uid, aid)


def borrar(uid, aid):
    with closing(db._con()) as con, con: return con.execute("DELETE FROM automatizaciones WHERE id=? AND user_id=?", (aid, uid)).rowcount > 0


def registro(uid, limite=200):
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute("SELECT * FROM automatizaciones_registro WHERE user_id=? ORDER BY ts DESC LIMIT ?", (uid, min(limite, MAX_REGISTRO)))]


def _en_horario(c, ref):
    n = ref.astimezone(tiempo.zona()); m = n.hour * 60 + n.minute
    def mins(x): return int(x[:2]) * 60 + int(x[3:])
    if c.get("dias") and n.weekday() not in c["dias"]: return False
    if "desde" in c:
        ini, fin = mins(c["desde"]), mins(c["hasta"])
        dentro = ini <= m <= fin if ini <= fin else m >= ini or m <= fin
        if not dentro: return False
    return True


def _condiciones_ok(r, evento, ref):
    c = r["condiciones"]
    if not _en_horario(c, ref): return False
    if "dispositivo_desconocido" in c and bool(evento.get("dispositivo_desconocido")) != c["dispositivo_desconocido"]: return False
    return True


async def _accion(uid, a, evento):
    tipo = a["tipo"]
    if tipo == "avisar": await avisos.emitir("automatizacion", "info", a["texto"], "automatizaciones", [uid], extra={"automatizacion": True})
    elif tipo == "pausar_internet_dispositivo":
        from . import control
        clave = evento.get("dispositivo") or evento.get("clave")
        if not clave: raise AutomatizacionError("El evento no identifica el dispositivo.")
        await asyncio.to_thread(control.pausar, clave, a.get("minutos")); await control.reconciliar()
    elif tipo == "pausar_bloqueador":
        from . import shield
        await shield.pausar(a["minutos"])
    elif tipo == "reanudar_bloqueador":
        from . import shield
        await shield.reanudar()
    elif tipo == "ejecutar_rutina":
        from . import rutinas
        r = await asyncio.to_thread(rutinas.obtener, uid, a["rutina_id"])
        if not r: raise AutomatizacionError("La rutina no existe.")
        await rutinas.ejecutar(r, canales_=[], ahora=time.time())
    elif tipo == "escanear_red":
        from . import escaneo
        await asyncio.to_thread(escaneo.solicitar, a.get("perfil", "rapido"), None, "automatizacion")
    return tipo


async def disparar(uid, r, evento, simular=False):
    ahora = time.time()
    if not simular and r["ultimo_disparo"] and ahora - r["ultimo_disparo"] < ANTI_BUCLE_S: return {"omitida": "anti_bucle"}
    if not simular:
        with closing(db._con()) as con, con:
            if con.execute("UPDATE automatizaciones SET ultimo_disparo=? WHERE id=? AND user_id=? AND (ultimo_disparo IS NULL OR ?-ultimo_disparo>=?)", (ahora, r["id"], uid, ahora, ANTI_BUCLE_S)).rowcount == 0: return {"omitida": "anti_bucle"}
    resultados = []
    try:
        for a in r["acciones"]: resultados.append(await _accion(uid, a, evento))
        estado = "ok"
    except Exception as e: estado = "error: " + str(e); log.exception("Automatización %s", r["id"])
    if not simular:
        with closing(db._con()) as con, con:
            con.execute("INSERT INTO automatizaciones_registro(automatizacion_id,user_id,ts,disparo,acciones,resultado) VALUES(?,?,?,?,?,?)", (r["id"], uid, ahora, json.dumps(evento, ensure_ascii=False)[:1000], json.dumps(resultados), estado))
            con.execute("DELETE FROM automatizaciones_registro WHERE user_id=? AND id NOT IN (SELECT id FROM automatizaciones_registro WHERE user_id=? ORDER BY ts DESC LIMIT ?)", (uid, uid, MAX_REGISTRO))
    return {"resultado": estado, "acciones": resultados}


async def evento(tipo, evento_):
    if evento_.get("automatizacion"): return []
    out = []
    for u in _usuarios():
        for r in listar(u["id"]):
            d = r["disparador"]
            if r["activa"] and d.get("tipo") == "aviso" and d.get("aviso") == tipo and _condiciones_ok(r, evento_, tiempo.ahora()):
                out.append(await disparar(u["id"], r, evento_))
    return out


def _usuarios():
    from . import usuarios
    return [u for u in usuarios.listar() if u["activo"] and u["rol"] == "admin"]


async def tick(ahora=None):
    ahora = time.time() if ahora is None else ahora; ref = datetime.fromtimestamp(ahora, tiempo.zona()); out = []
    for u in _usuarios():
        for r in listar(u["id"]):
            if not r["activa"] or not _condiciones_ok(r, {}, ref): continue
            d = r["disparador"]
            coincide = d.get("tipo") == "hora" and d.get("hora") == ref.strftime("%H:%M") and (not d.get("dias") or ref.weekday() in d["dias"])
            if d.get("tipo") == "umbral":
                from . import sistema
                valor = sistema.temperatura() if d["metrica"] == "temperatura" else None
                coincide = valor is not None and _OPS[d["operador"]](valor, d["valor"])
            if coincide: out.append(await disparar(u["id"], r, {"tipo": d["tipo"]}))
    return out
