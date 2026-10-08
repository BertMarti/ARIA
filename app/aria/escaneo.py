"""Lado de la app del escáner `aria-escaner` (comunicación por un volumen compartido, sin red ni socket).

La app escribe una petición JSON en `peticiones/` y el escáner (contenedor aparte con nmap) deja el
resultado en `resultados/` y su estado en `estado.json`. Ambos lados validan que los objetivos están
dentro de la red permitida y limitan la frecuencia.
"""
import json
import os
import secrets
import time
from pathlib import Path

from . import config
from .escaneo_comun import PERFILES, ObjetivoNoPermitido, validar_objetivos

INTERVALO_MIN_S = 10 * 60   # un escaneo bajo demanda cada 10 minutos como mucho
_ID_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


class EscaneoError(Exception):
    """Error legible (en español)."""


def _dir(nombre: str) -> Path:
    return config.ESCANER_DIR / nombre


def disponible() -> bool:
    return config.ESCANER_DIR.is_dir()


def _leer_json(ruta: Path):
    try:
        return json.loads(ruta.read_text())
    except (OSError, ValueError):
        return None


def estado() -> dict:
    e = _leer_json(config.ESCANER_DIR / "estado.json") or {}
    pend = sorted(p.stem for p in _dir("peticiones").glob("*.json")) if _dir("peticiones").is_dir() else []
    ult = ultimo()
    return {"disponible": disponible(), "escaner_vivo": bool(e) and time.time() - e.get("latido", 0) < 120,
            "en_curso": e.get("en_curso"), "siguiente_programado": e.get("siguiente_programado"),
            "ultimo_error": e.get("ultimo_error"), "pendientes": len(pend),
            "ultimo": {k: ult.get(k) for k in ("id", "perfil", "origen", "inicio", "fin")} | {
                "hosts": len(ult.get("hosts") or [])} if ult else None}


def solicitar(perfil: str = "rapido", objetivos=None, origen: str = "manual") -> str:
    if perfil not in PERFILES:
        raise EscaneoError("Perfil de escaneo desconocido.")
    try:
        objs = validar_objetivos(objetivos or [config.RED_PERMITIDA], config.RED_PERMITIDA)
    except ObjetivoNoPermitido as e:
        raise EscaneoError(str(e)) from None
    if not disponible():
        raise EscaneoError("El escáner no está instalado (falta el volumen compartido de aria-escaner).")
    e = estado()
    if e["pendientes"] or e["en_curso"]:
        raise EscaneoError("Ya hay un escaneo pendiente o en curso; espera a que termine.")
    ultima = (_leer_json(config.ESCANER_DIR / "ultima_peticion.json") or {}).get("ts", 0)
    if time.time() - ultima < INTERVALO_MIN_S:
        falta = int(INTERVALO_MIN_S - (time.time() - ultima)) // 60 + 1
        raise EscaneoError(f"Solo se permite un escaneo cada 10 minutos. Prueba dentro de {falta} min.")
    pid = time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    datos = {"id": pid, "perfil": perfil, "objetivos": objs, "origen": origen, "solicitado": time.time()}
    _dir("peticiones").mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(_dir("peticiones"), 0o2770)  # el escáner (mismo grupo) debe poder borrarlas
    except PermissionError:
        pass
    tmp = _dir("peticiones") / f".{pid}.tmp"
    tmp.write_text(json.dumps(datos))
    os.chmod(tmp, 0o660)
    tmp.replace(_dir("peticiones") / f"{pid}.json")
    marca_tmp = config.ESCANER_DIR / ".ultima_peticion.tmp"
    marca_tmp.write_text(json.dumps({"ts": time.time()}))
    marca_tmp.replace(config.ESCANER_DIR / "ultima_peticion.json")
    return pid


def resultados(n: int = 10) -> list:
    d = _dir("resultados")
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.json"), reverse=True):
        if not set(p.stem) <= _ID_OK:
            continue
        j = _leer_json(p)
        if isinstance(j, dict) and isinstance(j.get("hosts"), list):
            out.append(j)
        if len(out) >= n:
            break
    return sorted(out, key=lambda r: r.get("fin") or 0, reverse=True)


def vecinos(max_edad_s: float = 300) -> dict:
    """IP -> MAC vistos ahora mismo por la Raspberry (lo publica aria-escaner cada minuto)."""
    v = _leer_json(config.ESCANER_DIR / "vecinos.json") or {}
    if not isinstance(v, dict) or time.time() - float(v.get("ts") or 0) > max_edad_s:
        return {}
    return {str(ip): str(mac).upper() for ip, mac in (v.get("vecinos") or {}).items()}


def ultimo() -> dict | None:
    r = resultados(1)
    return r[0] if r else None


def anterior_a(rid: str) -> dict | None:
    """Resultado completo anterior (para detectar puertos nuevos)."""
    lista = resultados(10)
    ids = [r.get("id") for r in lista]
    if rid in ids:
        i = ids.index(rid)
        return next((r for r in lista[i + 1:] if not r.get("error")), None)
    return None
