"""Estado de la Raspberry Pi leído de /proc y /sys (valores del anfitrión)."""
import shutil
from pathlib import Path

from . import config

RUTA_TEMP = Path("/sys/class/thermal/thermal_zone0/temp")


def _leer(ruta) -> str | None:
    try:
        return Path(ruta).read_text()
    except OSError:
        return None


def temperatura() -> float | None:
    t = _leer(RUTA_TEMP)
    try:
        return round(int(t) / 1000, 1) if t else None
    except ValueError:
        return None


def memoria() -> dict | None:
    txt = _leer("/proc/meminfo")
    if not txt:
        return None
    kb = {}
    for linea in txt.splitlines():
        k, _, v = linea.partition(":")
        partes = v.split()
        if partes and partes[0].isdigit():
            kb[k] = int(partes[0])
    total, disp = kb.get("MemTotal"), kb.get("MemAvailable")
    if not total or disp is None:
        return None
    usada = total - disp
    return {"total": total * 1024, "usada": usada * 1024, "disponible": disp * 1024,
            "porcentaje": round(usada * 100 / total, 1)}


def carga() -> list | None:
    t = _leer("/proc/loadavg")
    try:
        return [float(x) for x in t.split()[:3]] if t else None
    except ValueError:
        return None


def uptime_seg() -> int | None:
    t = _leer("/proc/uptime")
    try:
        return int(float(t.split()[0])) if t else None
    except (ValueError, IndexError):
        return None


def disco() -> dict | None:
    try:
        d = shutil.disk_usage(config.DATA_DIR if config.DATA_DIR.exists() else "/")
    except OSError:
        return None
    return {"total": d.total, "usado": d.used, "libre": d.free, "porcentaje": round(d.used * 100 / d.total, 1)}


def formato_uptime(seg: int | None) -> str:
    if seg is None:
        return "desconocido"
    d, r = divmod(seg, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d} d {h} h"
    return f"{h} h {m} min" if h else f"{m} min"


def estado() -> dict:
    return {"temperatura": temperatura(), "memoria": memoria(), "carga": carga(),
            "uptime": uptime_seg(), "uptime_texto": formato_uptime(uptime_seg()), "disco": disco()}
