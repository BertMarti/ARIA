"""Lectura y persistencia de la telemetría producida por el agente del host."""
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import closing
from pathlib import Path

from . import config, db

MAX_EDAD = 30
_rachas = defaultdict(int)
_ultimo_minuto = None
_ultima_peticion = 0.0


def _host() -> Path:
    return config.DATA_DIR / "host"


def _leer(nombre: str):
    try:
        return json.loads((_host() / nombre).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _validar(d):
    if not isinstance(d, dict) or not isinstance(d.get("ts"), (int, float)):
        return None
    if time.time() - float(d["ts"]) > MAX_EDAD:
        return None
    sistema = d.get("sistema")
    if not isinstance(sistema, dict):
        return None
    return d


def leer() -> dict:
    d = _leer("telemetria.json")
    if d is None:
        raise RuntimeError("El sistema en directo no está disponible. Comprueba sistema/instalar-host-agente.sh.")
    if _validar(d) is None:
        raise RuntimeError("El agente del host no está activo (telemetría de hace más de 30 s). "
                           "Comprueba sistema/instalar-host-agente.sh.")
    guardar_muestra(d)
    return d


def _numero(v, defecto=0.0):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else defecto


def estados(d: dict) -> dict:
    s = d.get("sistema") or {}
    cont = d.get("contenedores") or []
    valores = {
        "cpu": _numero(s.get("cpu")),
        "temperatura": _numero(s.get("temperatura"), None),
        "memoria": max((_numero(c.get("memoria"), 0) for c in cont), default=0),
    }
    activos = {}
    for clave, problema in (("cpu", valores["cpu"] > 90), ("temperatura", valores["temperatura"] is not None and valores["temperatura"] > 75)):
        _rachas[clave] = _rachas[clave] + 1 if problema else 0
        activos[clave] = {"activo": _rachas[clave] >= 2, "racha": _rachas[clave]}
    for c in cont:
        nombre = str(c.get("nombre") or "")
        cpu = _numero(c.get("cpu")) > 80
        memoria = _numero(c.get("memoria"), 0) > 1_500_000_000
        clave = "contenedor:" + nombre
        _rachas[clave] = _rachas[clave] + 1 if cpu else 0
        activos[clave] = {"activo": _rachas[clave] >= 5 or memoria, "racha": _rachas[clave],
                          "nombre": nombre, "memoria": memoria}
    return {"cpu": activos["cpu"], "temperatura": activos["temperatura"],
            "contenedores": [v for k, v in activos.items() if k.startswith("contenedor:")]}


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS telemetria_historial (
            instante INTEGER PRIMARY KEY, cpu REAL, temperatura REAL, memoria REAL, contenedores TEXT)""")
        columnas = {r["name"] for r in con.execute("PRAGMA table_info(telemetria_historial)")}
        if "contenedores" not in columnas:
            con.execute("ALTER TABLE telemetria_historial ADD COLUMN contenedores TEXT NOT NULL DEFAULT '[]'")


def guardar_muestra(d: dict) -> None:
    global _ultimo_minuto
    instante = int(float(d["ts"]) // 60 * 60)
    if instante == _ultimo_minuto:
        return
    _ultimo_minuto = instante
    cs = d.get("contenedores") or []
    memoria = sum(_numero(c.get("memoria"), 0) for c in cs)
    s = d.get("sistema") or {}
    with closing(db._con()) as con, con:
        con.execute("INSERT OR REPLACE INTO telemetria_historial VALUES (?,?,?,?,?)",
                    (instante, _numero(s.get("cpu")), s.get("temperatura"), memoria, json.dumps(cs)))
        limite = time.time() - 7 * 86400
        con.execute("DELETE FROM telemetria_historial WHERE instante<?", (limite,))
        con.execute("DELETE FROM telemetria_historial WHERE instante<? AND (instante / 60) % 15 != 0",
                    (time.time() - 86400,))


def historial(horas: int) -> list:
    if horas not in (1, 24, 168):
        raise ValueError("Las horas deben ser 1, 24 o 168.")
    with closing(db._con()) as con:
        filas = con.execute("SELECT instante, cpu, temperatura, memoria, contenedores FROM telemetria_historial "
                            "WHERE instante>=? ORDER BY instante", (time.time() - horas * 3600,)).fetchall()
    return [{"ts": r["instante"], "cpu": r["cpu"], "temperatura": r["temperatura"], "memoria": r["memoria"],
             "contenedores": json.loads(r["contenedores"] or "[]")} for r in filas]


def directo() -> dict:
    d = leer()
    return {**d, "umbrales": estados(d)}


def solicitar_reinicio() -> dict:
    global _ultima_peticion
    ahora = time.time()
    if ahora - _ultima_peticion < 600:
        raise RuntimeError("Solo se puede solicitar un reinicio cada 10 minutos.")
    ts = int(ahora)
    nonce = secrets.token_hex(16)
    firma = hmac.new(config.SECRET.encode(), f"reiniciar:{ts}:{nonce}".encode(), hashlib.sha256).hexdigest()
    destino = _host() / "peticiones" / "reinicio.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".tmp")
    temporal.write_text(json.dumps({"ts": ts, "nonce": nonce, "firma": firma}), encoding="utf-8")
    os.chmod(temporal, 0o660)
    temporal.replace(destino)
    _ultima_peticion = ahora
    return {"programado": True, "segundos": 15}


def texto() -> str:
    d = directo()
    cs = sorted(d.get("contenedores") or [], key=lambda c: _numero(c.get("cpu")), reverse=True)
    cpu = _numero((d.get("sistema") or {}).get("cpu"))
    extra = f"; lo que más consume es {cs[0].get('nombre')} ({_numero(cs[0].get('cpu')):.0f} %)" if cs else ""
    return f"La Pi va al {cpu:.0f} % de CPU{extra}."
