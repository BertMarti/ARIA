"""Cámaras Tapo con python-kasa (local, con la cuenta TP-Link). Hoy: estado y modo privacidad (tapar la lente)."""
import asyncio

from . import config

_conexiones: dict = {}
_conocidas: set = set()   # IPs de cámaras vistas (para no aceptar órdenes a IPs cualquiera)
TIMEOUT = 8


class TapoError(Exception):
    pass


def configurado() -> bool:
    return bool(config.TAPO_USUARIO and config.TAPO_PASSWORD)


def _credenciales():
    from kasa import Credentials
    return Credentials(config.TAPO_USUARIO, config.TAPO_PASSWORD)


async def _conectar(ip: str):
    if ip in _conexiones:
        return _conexiones[ip]
    from kasa import Discover
    try:
        dev = await asyncio.wait_for(Discover.discover_single(ip, credentials=_credenciales()), TIMEOUT)
        await asyncio.wait_for(dev.update(), TIMEOUT)
    except Exception as e:  # noqa: BLE001
        raise TapoError("No se pudo conectar con la cámara.") from e
    _conexiones[ip] = dev
    return dev


async def _ips() -> list:
    if config.TAPO_CAMARAS:
        return list(config.TAPO_CAMARAS)
    from kasa import Discover
    try:
        encontrados = await asyncio.wait_for(Discover.discover(timeout=4, credentials=_credenciales()), TIMEOUT)
    except Exception:  # noqa: BLE001
        return []
    return [ip for ip, d in encontrados.items() if "LensMask" in getattr(d, "modules", {}) or
            type(d).__name__ == "SmartCamDevice"]


def _fila(ip: str, dev) -> dict:
    modulos = getattr(dev, "modules", {})
    fila = {"ip": ip, "modelo": getattr(dev, "model", "") or "Tapo", "nombre": getattr(dev, "alias", "") or ip,
            "en_linea": True}
    mascara = modulos.get("LensMask") if hasattr(modulos, "get") else None
    if mascara is not None:
        fila["privacidad"] = bool(mascara.enabled)
    movimiento = modulos.get("MotionDetection") if hasattr(modulos, "get") else None
    if movimiento is not None and hasattr(movimiento, "enabled"):
        fila["deteccion_movimiento"] = bool(movimiento.enabled)
    return fila


async def camaras() -> list:
    if not configurado():
        return []
    salida = []
    for ip in await _ips():
        try:
            dev = await _conectar(ip)
            await asyncio.wait_for(dev.update(), TIMEOUT)
            salida.append(_fila(ip, dev))
            _conocidas.add(ip)
        except Exception:  # noqa: BLE001 - una cámara apagada no tumba a las demás
            _conexiones.pop(ip, None)
            salida.append({"ip": ip, "modelo": "Tapo", "nombre": ip, "en_linea": False})
    return salida


async def privacidad(ip: str, activa: bool) -> dict:
    if ip not in config.TAPO_CAMARAS and ip not in _conocidas:
        raise TapoError("Cámara no encontrada.")
    dev = await _conectar(ip)
    mascara = dev.modules.get("LensMask") if hasattr(dev.modules, "get") else None
    if mascara is None:
        raise TapoError("Esta cámara no permite el modo privacidad.")
    try:
        await asyncio.wait_for(mascara.set_enabled(bool(activa)), TIMEOUT)
        await asyncio.wait_for(dev.update(), TIMEOUT)
    except Exception as e:  # noqa: BLE001
        _conexiones.pop(ip, None)
        raise TapoError("La cámara no ha respondido.") from e
    return _fila(ip, dev)


async def cerrar() -> None:
    for dev in list(_conexiones.values()):
        try:
            await dev.disconnect()
        except Exception:  # noqa: BLE001
            pass
    _conexiones.clear()
