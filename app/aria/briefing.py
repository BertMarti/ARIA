"""Resumen de buenos días: datos por usuario y día (caché en `resumen_dia`), tarjeta de Inicio y versión hablada.

Los datos solo de administrador (dispositivos VPN y copia fuera de la Pi) se quitan en el servidor
para el rol `usuario`, tanto al construirlos como al servir la caché."""
import asyncio
import copy
import json
import logging
import random
import re
import subprocess
import time
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from . import config, db, memoria, shield, sistema, tiempo, vpn

log = logging.getLogger("aria.briefing")

SOLO_ADMIN = ("vpn", "copia")  # claves de datos["casa"] que ve solo el administrador
RETENCION_DIAS = 4
COPIA_ANTIGUA_H = 36

# --- Saludo -----------------------------------------------------------------------------------------
_INICIO = {"hola", "holi", "ola", "hey", "ey", "hello", "saludos", "buenas", "buenos", "buen"}
_RESTO = {"dias", "dia", "tardes", "noches", "que", "tal", "como", "estas", "andas", "va", "todo", "a", "todos",
          "de", "nuevo", "otra", "vez", "aria", "bien"}


def es_saludo(texto: str) -> bool:
    """«hola», «buenos días», «buenas, ¿qué tal?»... pero no «hola, ¿qué temperatura hace?»."""
    p = memoria.normalizar(texto).split()
    return 0 < len(p) <= 7 and all(w in _INICIO or w in _RESTO for w in p) and any(w in _INICIO for w in p)


# --- Fuentes de datos ------------------------------------------------------------------------------------
def _edad(t: datetime, ahora: datetime | None = None) -> str:
    s = max(0, ((ahora or datetime.now(t.tzinfo)) - t).total_seconds())
    if s < 3600:
        return f"hace {max(1, int(s // 60))} min"
    if s < 86400:
        return f"hace {int(s // 3600)} h"
    return f"hace {int(s // 86400)} d"


def ultima_copia() -> dict:
    """Fecha de la última copia cifrada fuera de la Pi (commit más reciente de homelab-*.tar.gz.gpg).
    Solo si el repositorio está montado en el contenedor; si no, «no disponible»."""
    repo = Path(config.COPIAS_REPO)
    if not repo.is_dir():
        return {"disponible": False}
    try:
        r = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%cI", "--", "homelab-*.tar.gz.gpg"],
                           capture_output=True, text=True, timeout=6, check=False)
        t = datetime.fromisoformat(r.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return {"disponible": False}
    horas = (datetime.now(t.tzinfo) - t).total_seconds() / 3600
    return {"disponible": True, "fecha": t.isoformat(), "hace": _edad(t), "antigua": horas > COPIA_ANTIGUA_H}


async def _anuncios(ayer: date) -> dict | None:
    if not shield.configurado():
        return None
    try:
        ini, fin = tiempo.limites(ayer)
        d = await shield.resumen_dia(ini, fin)
        if d:
            return {"dia": "ayer", **d}
        r = await shield.resumen()  # Pi-hole sin datos de ayer (recién instalado): últimas 24 h
        return {"dia": "24h", "consultas": r["consultas"], "bloqueadas": r["bloqueadas"], "porcentaje": r["porcentaje"]}
    except shield.ShieldError:
        return None


async def _vpn() -> dict:
    if not vpn.configurado():
        return {"disponible": False}
    try:
        cl = await vpn.listar()
    except vpn.VpnError:
        return {"disponible": False}
    ahora = datetime.now().astimezone()
    recientes = []
    for c in cl:
        try:
            t = datetime.fromisoformat((c.get("ultimo_handshake") or "").replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=ahora.tzinfo)
        except ValueError:
            continue
        if (ahora - t) < timedelta(hours=24):
            recientes.append(c["nombre"])
    return {"disponible": True, "total": len(cl), "conectados": sum(1 for c in cl if c["conectado"]),
            "ultimas_24h": recientes[:8]}


def _sistema() -> dict | None:
    e = sistema.estado()
    if e["temperatura"] is None and not e["memoria"] and not e["disco"]:
        return None
    return {"temperatura": e["temperatura"], "ram": round(e["memoria"]["porcentaje"]) if e["memoria"] else None,
            "disco": round(e["disco"]["porcentaje"]) if e["disco"] else None, "uptime": e["uptime_texto"]}


_CODIGOS = [(0, "despejado"), (2, "poco nuboso"), (3, "nublado"), (48, "niebla"), (57, "llovizna"), (67, "lluvia"),
            (77, "nieve"), (82, "chubascos"), (86, "chubascos de nieve"), (99, "tormenta")]


def _cielo(codigo: int) -> str:
    return next((t for tope, t in _CODIGOS if codigo <= tope), "variable")


def _ruta_ciudad() -> Path:
    return config.DATA_DIR / "ciudad.json"


async def _coordenadas(cliente: httpx.AsyncClient) -> dict | None:
    """Coordenadas de ARIA_CIUDAD: ARIA_LAT/ARIA_LON si existen; si no, se geocodifica una sola vez
    (resultado en data/ciudad.json). «Ciudad, Provincia» elige el resultado de ES cuya provincia coincide."""
    if config.LAT is not None and config.LON is not None:
        return {"nombre": config.CIUDAD.split(",")[0].strip() or "tu ciudad", "lat": config.LAT, "lon": config.LON}
    try:
        d = json.loads(_ruta_ciudad().read_text())
        if d.get("consulta") == config.CIUDAD and "lat" in d:
            return d
    except (OSError, ValueError):
        pass
    nombre, _, zona_ = (x.strip() for x in config.CIUDAD.partition(","))
    r = await cliente.get("https://geocoding-api.open-meteo.com/v1/search",
                          params={"name": nombre, "count": 20, "language": "es", "format": "json"})
    res = r.json().get("results") or []
    z = memoria.normalizar(zona_)
    cand = [x for x in res if x.get("country_code") == "ES"] or res
    if z:
        cand = [x for x in cand if z in memoria.normalizar(f"{x.get('admin1', '')} {x.get('admin2', '')}")] or cand
    if not cand:
        return None
    x = cand[0]
    d = {"consulta": config.CIUDAD, "nombre": x.get("name") or nombre, "lat": x["latitude"], "lon": x["longitude"]}
    try:
        _ruta_ciudad().write_text(json.dumps(d))
    except OSError:
        pass
    return d


async def _tiempo() -> dict | None:
    if not config.CIUDAD and config.LAT is None:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            ub = await _coordenadas(c)
            if not ub:
                return None
            r = await c.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": ub["lat"], "longitude": ub["lon"], "timezone": config.TZ, "forecast_days": 1,
                "current": "temperature_2m,weather_code",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
            j = r.json()
            d = j["daily"]
            actual = (j.get("current") or {}).get("temperature_2m")
            return {"ciudad": ub["nombre"], "cielo": _cielo(int(d["weather_code"][0])),
                    "max": round(d["temperature_2m_max"][0]), "min": round(d["temperature_2m_min"][0]),
                    "lluvia": d["precipitation_probability_max"][0],
                    "actual": round(actual) if actual is not None else None}
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None


def recuerdos_de_hoy(uid: int, dia: date, n: int = 2) -> list:
    """1–2 recuerdos que pueden venir al caso hoy: primero los que nombran el día de la semana o el mes;
    después otros elegidos al azar (estable durante el día)."""
    hechos = memoria.listar(uid)
    claves = {memoria.normalizar(tiempo.DIAS[dia.weekday()]), memoria.normalizar(tiempo.MESES[dia.month - 1]), "hoy"}
    con_pista = [h for h in hechos if claves & set(memoria.normalizar(h["texto"]).split())]
    resto = [h for h in hechos if h not in con_pista]
    random.Random(f"{uid}-{dia.isoformat()}").shuffle(resto)
    return [h["texto"] for h in (con_pista + resto)[:n]]


# --- Construcción y caché ------------------------------------------------------------------------------
async def construir(usuario: dict, ref: datetime | None = None) -> dict:
    uid, admin = usuario["id"], usuario["rol"] == "admin"
    hoy = tiempo.hoy(ref)
    ayer = hoy - timedelta(days=1)
    anuncios, tmp, vpn_d = await asyncio.gather(_anuncios(ayer), _tiempo(), _vpn() if admin else asyncio.sleep(0))
    d_ayer = await asyncio.to_thread(memoria.dia, uid, ayer.isoformat())
    casa = {"anuncios": anuncios, "sistema": await asyncio.to_thread(_sistema)}
    if admin:
        casa["vpn"] = vpn_d
        casa["copia"] = await asyncio.to_thread(ultima_copia)
    nombre = memoria.limpiar(usuario.get("nombre"))
    saludo = tiempo.saludo_horario(ref)
    return {"fecha": hoy.isoformat(), "fecha_texto": tiempo.texto_fecha(hoy),
            "saludo": f"{saludo}, {nombre}" if nombre else saludo,
            "ayer": {"fecha": d_ayer["fecha"], "resumen": d_ayer["resumen"]} if d_ayer else None,
            "casa": casa, "recuerdos": await asyncio.to_thread(recuerdos_de_hoy, uid, hoy),
            "tiempo": tmp, "generado": time.time()}


def para_rol(datos: dict, rol: str) -> dict:
    """Copia sin los datos solo de administrador cuando el rol no es admin."""
    out = copy.deepcopy(datos)
    if rol != "admin":
        for k in SOLO_ADMIN:
            out.get("casa", {}).pop(k, None)
    return out


def _leer(uid: int, fecha: str) -> tuple[dict | None, bool]:
    with closing(db._con()) as con:
        r = con.execute("SELECT datos, saludado FROM resumen_dia WHERE user_id=? AND fecha=?", (uid, fecha)).fetchone()
    if not r:
        return None, False
    try:
        return json.loads(r["datos"]), bool(r["saludado"])
    except ValueError:
        return None, bool(r["saludado"])


def _guardar(uid: int, fecha: str, datos: dict) -> None:
    corte = (date.fromisoformat(fecha) - timedelta(days=RETENCION_DIAS)).isoformat()
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO resumen_dia (user_id, fecha, datos, saludado, creado) VALUES (?,?,?,0,?) "
                    "ON CONFLICT(user_id, fecha) DO UPDATE SET datos=excluded.datos, creado=excluded.creado",
                    (uid, fecha, json.dumps(datos, ensure_ascii=False), time.time()))
        con.execute("DELETE FROM resumen_dia WHERE user_id=? AND fecha<?", (uid, corte))


async def obtener(usuario: dict, refrescar: bool = False, ref: datetime | None = None) -> dict:
    """Resumen de hoy para este usuario: de la caché del día, o construido (y guardado) si no existe o se pide refrescar."""
    fecha = tiempo.hoy(ref).isoformat()
    if not refrescar:
        datos, _ = await asyncio.to_thread(_leer, usuario["id"], fecha)
        if datos:
            return para_rol(datos, usuario["rol"])
    datos = await construir(usuario, ref)
    await asyncio.to_thread(_guardar, usuario["id"], fecha, datos)
    return para_rol(datos, usuario["rol"])


def saludado_hoy(uid: int, ref: datetime | None = None) -> bool:
    return _leer(uid, tiempo.hoy(ref).isoformat())[1]


def marcar_saludado(uid: int, ref: datetime | None = None) -> None:
    with closing(db._con()) as con, con:
        con.execute("UPDATE resumen_dia SET saludado=1 WHERE user_id=? AND fecha=?", (uid, tiempo.hoy(ref).isoformat()))


# --- Versión hablada (chat) ------------------------------------------------------------------------------
def _n(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def _dec(v) -> str:
    return str(v).replace(".", ",")


def texto_hablado(d: dict) -> str:
    """Versión corta, en tono de conversación, del resumen (para responder a «hola» a primera hora)."""
    partes = [f"{d['saludo']}. Hoy es {d['fecha_texto']}."]
    t = d.get("tiempo")
    if t:
        ahora = f" Ahora hay {t['actual']} grados." if t.get("actual") is not None else ""
        lluvia = f" Probabilidad de lluvia: {t['lluvia']} %." if t.get("lluvia") is not None else ""
        partes.append(f"En {t['ciudad']} hoy habrá {t['cielo']}, entre {t['min']} y {t['max']} grados.{ahora}{lluvia}")
    if d.get("ayer"):
        lineas = [l.lstrip("-• ").strip() for l in d["ayer"]["resumen"].splitlines() if l.strip()]
        partes.append("Ayer: " + "; ".join(lineas[:3]).rstrip(".") + ".")
    casa = d.get("casa", {})
    c = []
    a = casa.get("anuncios")
    if a:
        cuando = "ayer" if a["dia"] == "ayer" else "en las últimas 24 horas"
        c.append(f"{cuando} se bloquearon {_n(a['bloqueadas'])} anuncios ({_dec(a['porcentaje'])} % de las consultas)")
    v = casa.get("vpn")
    if v and v.get("disponible"):
        x = f"en la VPN hay {v['conectados']} de {v['total']} dispositivos conectados"
        if v["ultimas_24h"]:
            x += ", y en las últimas 24 horas se conectaron " + ", ".join(v["ultimas_24h"])
        c.append(x)
    s = casa.get("sistema")
    if s:
        x = []
        if s.get("temperatura") is not None:
            x.append(f"la Raspberry está a {_dec(s['temperatura'])} grados")
        if s.get("ram") is not None:
            x.append(f"la RAM al {s['ram']} %")
        if s.get("disco") is not None:
            x.append(f"el disco al {s['disco']} %")
        if x:
            c.append(", ".join(x))
    cp = casa.get("copia")
    if cp is not None:
        c.append("la última copia de seguridad fuera de casa fue " + cp["hace"] if cp.get("disponible")
                 else "la última copia fuera de casa no está disponible")
    if c:
        partes.append("En casa: " + "; ".join(c) + ".")
    if d.get("recuerdos"):
        partes.append("Por cierto, recuerdo que " + d["recuerdos"][0].rstrip(".") + ".")
    return " ".join(partes)
