"""Informe de arranque: si la Raspberry se ha reiniciado (cambia el «btime» del kernel, que el contenedor
ve igual que el sistema), ARIA espera a que vuelvan los servicios y avisa a los administradores de cuánto
tiempo estuvo sin servicio y de cómo está todo. Un simple reinicio del contenedor no genera informe.

El latido (`data/latido.json`, cada minuto) da la hora aproximada a la que se apagó."""
import asyncio
import json
import logging
import time
from datetime import datetime

import httpx

from . import avisos, avisos_chequeos, config, sistema, tiempo

log = logging.getLogger("aria.arranque")

LATIDO_S = 60
ESPERA_MAX_S = 300       # como mucho se esperan 5 min a que todo esté listo antes de informar
ESPERA_PASO_S = 15
PRUEBA_INTERNET = "https://www.google.com/generate_204"


def arranque_kernel() -> float | None:
    """Instante (epoch) en que arrancó el sistema, según /proc/stat."""
    try:
        with open("/proc/stat", encoding="ascii") as f:
            for linea in f:
                if linea.startswith("btime "):
                    return float(linea.split()[1])
    except OSError:
        pass
    return None


def _leer(nombre: str) -> dict:
    try:
        return json.loads((config.DATA_DIR / nombre).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _escribir(nombre: str, datos: dict) -> None:
    try:
        ruta = config.DATA_DIR / nombre
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(datos), encoding="utf-8")
        tmp.replace(ruta)
    except OSError:
        log.warning("No se pudo guardar %s", nombre)


def duracion(segundos: float) -> str:
    s = max(0, int(segundos))
    if s < 60:
        return f"{s} s"
    m = s // 60
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{h // 24} días"


def _hora(ts: float) -> str:
    return datetime.fromtimestamp(ts, tiempo.zona()).strftime("%H:%M")


async def _internet() -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            return (await c.get(PRUEBA_INTERNET)).status_code in (200, 204)
    except httpx.HTTPError:
        return False


async def comprobar() -> dict:
    """Estado de cada pieza: True = bien, False = mal, None = no configurado."""
    async def ok(f):
        try:
            r = await f()
        except Exception:  # noqa: BLE001 - un chequeo roto cuenta como fallo, no rompe el informe
            return False
        return None if r is None else not r
    return {"Internet": await _internet(),
            "SHIELD-DNS (bloqueador)": await ok(avisos_chequeos.shield_dns),
            "HEIMDALL (VPN)": await ok(avisos_chequeos.heimdall),
            "Acceso desde fuera (túnel)": await ok(avisos_chequeos.tunel)}


def informe(btime: float, latido: float | None, estado: dict, ahora: float) -> str:
    lineas = ["🔌 La Raspberry se ha reiniciado y ARIA vuelve a estar en marcha."]
    if latido and latido < btime:
        lineas.append(f"Sin servicio desde las {_hora(latido)} hasta las {_hora(btime)} "
                      f"(unos {duracion(btime - latido)}); mientras tanto la casa usó el DNS de respaldo del router.")
    else:
        lineas.append(f"Arrancó a las {_hora(btime)}.")
    lineas.append(f"Todo listo {duracion(ahora - btime)} después de encenderse.")
    lineas.append("")
    for nombre, v in estado.items():
        if v is not None:
            lineas.append(f"{'✅' if v else '❌'} {nombre}")
    t = sistema.temperatura()
    if t is not None:
        lineas.append(f"🌡️ Temperatura: {str(t).replace('.', ',')} °C")
    if any(v is False for v in estado.values()):
        lineas.append("")
        lineas.append("Algo no ha vuelto: la autocuración lo reintentará y te avisaré si sigue caído.")
    return "\n".join(lineas)


async def revisar(latido: float | None = None, espera_max: float = ESPERA_MAX_S, paso: float = ESPERA_PASO_S) -> str | None:
    """Si el sistema se ha reiniciado desde la última vez, espera a los servicios y envía el informe.
    Devuelve el texto enviado (o None si no tocaba)."""
    btime = arranque_kernel()
    previo = _leer("arranque.json").get("btime")
    if not btime:
        return None
    if previo is None or abs(btime - previo) < 5:   # primera vez o mismo arranque (solo se reinició ARIA)
        _escribir("arranque.json", {"btime": btime})
        return None
    inicio = time.monotonic()
    estado = await comprobar()
    while any(v is False for v in estado.values()) and time.monotonic() - inicio < espera_max:
        await asyncio.sleep(paso)
        estado = await comprobar()
    texto = informe(btime, latido, estado, time.time())
    try:
        await avisos.emitir("sistema", "info", texto)
    finally:
        _escribir("arranque.json", {"btime": btime})  # aunque falle el envío: no se repite en cada reinicio de ARIA
    return texto


async def _revisar_seguro(latido: float | None, retraso: float) -> None:
    await asyncio.sleep(retraso)  # deja que Telegram y los demás canales arranquen
    try:
        await revisar(latido)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        log.exception("No se pudo preparar el informe de arranque")


async def bucle(retraso: float = 30) -> None:
    latido = _leer("latido.json").get("ts")  # se lee antes de escribir el latido nuevo
    tarea = asyncio.create_task(_revisar_seguro(latido, retraso))
    try:
        while True:
            _escribir("latido.json", {"ts": time.time()})
            await asyncio.sleep(LATIDO_S)
    finally:
        tarea.cancel()
