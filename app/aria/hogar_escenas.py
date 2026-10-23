"""Escenas de Hogar: varias luces y cámaras de una vez («Cine», «Buenas noches», «Me voy»…).

Cada acción dice qué hacer con una luz (encender con brillo o color, o apagar) o con la privacidad de una cámara. Al
ejecutarla se hacen todas aunque falle alguna, y se cuenta qué ha fallado. Solo administradores.
"""
import datetime as dt
import json
import math
import re
import time
from contextlib import closing

from . import config, db, hogar_cache, hogar_govee, hogar_tapo

MAX_ESCENAS = 12
MAX_ACCIONES = 20
ICONOS = ("luz", "cine", "noche", "salir", "casa", "fiesta", "lectura", "despertar")


class EscenaError(ValueError):
    pass


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS hogar_escenas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL UNIQUE COLLATE NOCASE, icono TEXT NOT NULL,
            acciones TEXT NOT NULL, creada REAL NOT NULL)""")


def _validar_accion(a) -> dict:
    if not isinstance(a, dict):
        raise EscenaError("Acción no válida.")
    if a.get("tipo") == "luz":
        if not isinstance(a.get("id"), str) or not 1 <= len(a["id"]) <= 64:
            raise EscenaError("Luz no válida.")
        if not isinstance(a.get("encendida"), bool):
            raise EscenaError("Di si la luz se enciende o se apaga.")
        salida = {"tipo": "luz", "id": a["id"], "encendida": a["encendida"]}
        if a["encendida"]:
            brillo, color = a.get("brillo"), a.get("color")
            if brillo is not None:
                if isinstance(brillo, bool) or not isinstance(brillo, int) or not 1 <= brillo <= 100:
                    raise EscenaError("El brillo debe estar entre 1 y 100.")
                salida["brillo"] = brillo
            if color is not None:
                if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                    raise EscenaError("El color debe tener formato #rrggbb.")
                salida["color"] = color.lower()
        return salida
    if a.get("tipo") == "camara":
        if not isinstance(a.get("ip"), str) or not isinstance(a.get("privacidad"), bool):
            raise EscenaError("Cámara no válida.")
        return {"tipo": "camara", "ip": a["ip"], "privacidad": a["privacidad"]}
    raise EscenaError("Acción no válida.")


def _validar(datos, conocidas: dict) -> tuple:
    """conocidas: {"luces": {id}, "camaras": {ip}} — solo se aceptan aparatos que ARIA ya conoce."""
    if not isinstance(datos, dict):
        raise EscenaError("Datos no válidos.")
    nombre = datos.get("nombre")
    if not isinstance(nombre, str) or not 1 <= len(nombre.strip()) <= 30:
        raise EscenaError("El nombre debe tener entre 1 y 30 caracteres.")
    icono = datos.get("icono", "luz")
    if icono not in ICONOS:
        raise EscenaError("Icono no válido.")
    acciones = datos.get("acciones")
    if not isinstance(acciones, list) or not 1 <= len(acciones) <= MAX_ACCIONES:
        raise EscenaError(f"Una escena necesita entre 1 y {MAX_ACCIONES} acciones.")
    limpias, vistos = [], set()
    for a in acciones:
        a = _validar_accion(a)
        clave = (a["tipo"], a.get("id") or a.get("ip"))
        if clave in vistos:
            raise EscenaError("Cada aparato solo puede salir una vez en la escena.")
        vistos.add(clave)
        if a["tipo"] == "luz" and a["id"] not in conocidas["luces"]:
            raise EscenaError("Esa luz no está en tu casa.")
        if a["tipo"] == "camara" and a["ip"] not in conocidas["camaras"]:
            raise EscenaError("Esa cámara no está en tu casa.")
        limpias.append(a)
    return nombre.strip(), icono, limpias


async def conocidas() -> dict:
    """Lo que hay en casa: lo último de la caché y, si se acaba de invalidar (tras un cambio), se vuelve a pedir."""
    luces = hogar_cache.ultimo("luces")
    if luces is None and hogar_govee.configurado():
        try:
            luces = await hogar_cache.obtener("luces", hogar_govee.luces, 300)
        except Exception:  # noqa: BLE001 - sin Govee no se puede elegir ninguna luz
            luces = []
    camaras = set(config.TAPO_CAMARAS) | {c.get("ip") for c in hogar_cache.ultimo("camaras") or [] if c.get("ip")}
    return {"luces": {x.get("id") for x in luces or [] if x.get("id")}, "camaras": camaras}


def _fila(f) -> dict:
    return {"id": f["id"], "nombre": f["nombre"], "icono": f["icono"], "acciones": json.loads(f["acciones"])}


def listar() -> list:
    iniciar()
    with closing(db._con()) as con:
        return [_fila(f) for f in con.execute("SELECT * FROM hogar_escenas ORDER BY id").fetchall()]


def obtener(eid: int) -> dict | None:
    iniciar()
    with closing(db._con()) as con:
        f = con.execute("SELECT * FROM hogar_escenas WHERE id=?", (eid,)).fetchone()
    return _fila(f) if f else None


def crear(datos, conocidas_: dict) -> dict:
    nombre, icono, acciones = _validar(datos, conocidas_)
    iniciar()
    with closing(db._con()) as con, con:
        if con.execute("SELECT COUNT(*) FROM hogar_escenas").fetchone()[0] >= MAX_ESCENAS:
            raise EscenaError(f"Como mucho {MAX_ESCENAS} escenas.")
        if con.execute("SELECT 1 FROM hogar_escenas WHERE nombre=?", (nombre,)).fetchone():
            raise EscenaError("Ya hay una escena con ese nombre.")
        cur = con.execute("INSERT INTO hogar_escenas(nombre, icono, acciones, creada) VALUES(?,?,?,?)",
                          (nombre, icono, json.dumps(acciones), time.time()))
        eid = cur.lastrowid
    return obtener(eid)


def actualizar(eid: int, datos, conocidas_: dict) -> dict | None:
    nombre, icono, acciones = _validar(datos, conocidas_)
    if obtener(eid) is None:
        return None
    with closing(db._con()) as con, con:
        if con.execute("SELECT 1 FROM hogar_escenas WHERE nombre=? AND id<>?", (nombre, eid)).fetchone():
            raise EscenaError("Ya hay una escena con ese nombre.")
        con.execute("UPDATE hogar_escenas SET nombre=?, icono=?, acciones=? WHERE id=?",
                    (nombre, icono, json.dumps(acciones), eid))
    return obtener(eid)


def borrar(eid: int) -> bool:
    iniciar()
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM hogar_escenas WHERE id=?", (eid,)).rowcount == 1


async def ejecutar(escena: dict) -> dict:
    """Hace todas las acciones; una que falla no para a las demás. Devuelve {"hechas": n, "fallidas": [nombres]}."""
    nombres = {x.get("id"): x.get("nombre") for x in hogar_cache.ultimo("luces") or []}
    nombres.update({c.get("ip"): c.get("nombre") for c in hogar_cache.ultimo("camaras") or []})
    hechas, fallidas = 0, []
    for a in escena["acciones"]:
        try:
            if a["tipo"] == "luz":
                color = int(a["color"][1:], 16) if a.get("color") else None
                await hogar_govee.cambiar(a["id"], a["encendida"], a.get("brillo"), color)
            else:
                await hogar_tapo.privacidad(a["ip"], a["privacidad"])
            hechas += 1
        except Exception:  # noqa: BLE001 - una luz sin conexión no estropea la escena
            nombre = nombres.get(a.get("id") or a.get("ip"))
            fallidas.append(nombre if nombre and nombre != a.get("ip") else ("una luz" if a["tipo"] == "luz" else "una cámara"))
    hogar_cache.invalidar("luces", "camaras")
    return {"hechas": hechas, "fallidas": fallidas}


# --- ¿Es de noche? (para «al llegar alguien de noche») --------------------------------------------------------------
def _sol(fecha: dt.date, lat: float, lon: float) -> tuple | None:
    """Salida y puesta del sol en UTC (horas decimales), algoritmo aproximado de NOAA (±2 min). None si no sale o no se pone."""
    n = fecha.timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (n - 1)
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(gamma) - 0.032077 * math.sin(gamma)
                    - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma) - 0.006758 * math.cos(2 * gamma)
            + 0.000907 * math.sin(2 * gamma) - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))
    phi = math.radians(lat)
    c = (math.cos(math.radians(90.833)) / (math.cos(phi) * math.cos(decl))) - math.tan(phi) * math.tan(decl)
    if not -1 <= c <= 1:
        return None
    ha = math.degrees(math.acos(c))
    salida = (720 - 4 * (lon + ha) - eqt) / 60
    puesta = (720 - 4 * (lon - ha) - eqt) / 60
    return salida, puesta


def es_de_noche(ahora: float | None = None) -> bool:
    """Con ARIA_LAT/ARIA_LON: entre la puesta y la salida del sol. Sin ellas: de 20:30 a 7:30, hora de casa."""
    ahora = time.time() if ahora is None else ahora
    if config.LAT is not None and config.LON is not None:
        momento = dt.datetime.fromtimestamp(ahora, dt.timezone.utc)
        sol = _sol(momento.date(), config.LAT, config.LON)
        if sol is not None:
            hora = momento.hour + momento.minute / 60 + momento.second / 3600
            salida, puesta = sol[0] % 24, sol[1] % 24
            de_dia = salida <= hora <= puesta if salida < puesta else (hora >= salida or hora <= puesta)
            return not de_dia
    try:
        from zoneinfo import ZoneInfo
        local = dt.datetime.fromtimestamp(ahora, ZoneInfo(config.TZ))
    except Exception:  # noqa: BLE001
        local = dt.datetime.fromtimestamp(ahora)
    minutos = local.hour * 60 + local.minute
    return minutos >= 20 * 60 + 30 or minutos < 7 * 60 + 30
