"""Cámaras Tapo con python-kasa (local, con la cuenta TP-Link): estado, ajustes, modo privacidad, movimiento y posiciones guardadas."""
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


# Ajustes que se pueden cambiar desde ARIA: campo de la API -> (módulo de python-kasa, lectura, escritura).
AJUSTES = {
    "privacidad": ("LensMask", "enabled", "set_enabled"),
    "movimiento": ("MotionDetection", "enabled", "set_enabled"),
    "personas": ("PersonDetection", "enabled", "set_enabled"),
    "led": ("Led", "led", "set_led"),
}
PASO_GIRO, PASO_INCLINACION = 30, 10
MOVIMIENTOS = {"izquierda": (PASO_GIRO, 0), "derecha": (-PASO_GIRO, 0), "arriba": (0, PASO_INCLINACION),
               "abajo": (0, -PASO_INCLINACION)}


def _fila(ip: str, dev) -> dict:
    modulos = getattr(dev, "modules", {})
    obtener = modulos.get if hasattr(modulos, "get") else (lambda _: None)
    fila = {"ip": ip, "modelo": getattr(dev, "model", "") or "Tapo", "nombre": (getattr(dev, "alias", "") or "").strip() or ip,
            "en_linea": True, "ptz": obtener("PanTilt") is not None}
    for campo, (modulo, lectura, _) in AJUSTES.items():
        m = obtener(modulo)
        if m is not None:
            try:
                fila[campo] = bool(getattr(m, lectura))
            except Exception:  # noqa: BLE001 - un dato que falta no tumba la ficha
                pass
    if "movimiento" in fila:
        fila["deteccion_movimiento"] = fila["movimiento"]   # nombre antiguo (pantalla anterior)
    bateria = obtener("Battery")
    if bateria is not None:
        try:
            fila["bateria"] = int(bateria.battery_percent)
        except Exception:  # noqa: BLE001
            pass
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


async def privacidad(ip: str, activa: bool) -> dict:   # (se mantiene: la usan la vigilancia y el chat)
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


async def ajustar(ip: str, campo: str, valor: bool) -> dict:
    """Cambia privacidad, detección de movimiento o personas, o el LED. Solo cámaras conocidas."""
    if campo not in AJUSTES:
        raise TapoError("Ajuste no válido.")
    if ip not in config.TAPO_CAMARAS and ip not in _conocidas:
        raise TapoError("Cámara no encontrada.")
    dev = await _conectar(ip)
    modulo, _, escritura = AJUSTES[campo]
    m = dev.modules.get(modulo) if hasattr(dev.modules, "get") else None
    if m is None:
        raise TapoError("Esta cámara no tiene ese ajuste.")
    try:
        await asyncio.wait_for(getattr(m, escritura)(bool(valor)), TIMEOUT)
        await asyncio.wait_for(dev.update(), TIMEOUT)
    except Exception as e:  # noqa: BLE001
        _conexiones.pop(ip, None)
        raise TapoError("La cámara no ha respondido.") from e
    return _fila(ip, dev)


async def mover(ip: str, direccion: str) -> None:
    """Gira o inclina una cámara motorizada (C520WS…) un paso."""
    if direccion not in MOVIMIENTOS:
        raise TapoError("Dirección no válida.")
    if ip not in config.TAPO_CAMARAS and ip not in _conocidas:
        raise TapoError("Cámara no encontrada.")
    dev = await _conectar(ip)
    motor = dev.modules.get("PanTilt") if hasattr(dev.modules, "get") else None
    if motor is None:
        raise TapoError("Esta cámara no se puede mover.")
    giro, inclinacion = MOVIMIENTOS[direccion]
    try:
        await asyncio.wait_for(motor.move(pan=giro, tilt=inclinacion), TIMEOUT)
    except Exception as e:  # noqa: BLE001
        if await _tapada(ip):
            raise TapoError(TAPADA) from e
        _conexiones.pop(ip, None)
        raise TapoError("La cámara no ha respondido.") from e


TAPADA = "La cámara está tapada (modo privacidad): destápala para moverla."


async def _tapada(ip: str) -> bool:
    """Con la privacidad puesta el motor no obedece (la C520WS contesta con un error genérico): se pregunta para
    explicarlo bien en lugar de decir que no ha respondido."""
    try:
        dev = await _conectar(ip)
        await asyncio.wait_for(dev.update(), TIMEOUT)
        lente = dev.modules.get("LensMask") if hasattr(dev.modules, "get") else None
        return bool(lente is not None and lente.enabled)
    except Exception:  # noqa: BLE001
        return False


# Posiciones guardadas (como en la app Tapo): la cámara las guarda en su memoria; ARIA solo las lista y las usa.
MAX_POSICIONES = 8


async def _motor(ip: str):
    if ip not in config.TAPO_CAMARAS and ip not in _conocidas:
        raise TapoError("Cámara no encontrada.")
    dev = await _conectar(ip)
    motor = dev.modules.get("PanTilt") if hasattr(dev.modules, "get") else None
    if motor is None:
        raise TapoError("Esta cámara no se puede mover.")
    return dev, motor


def _comprobar(respuesta) -> None:
    """Una respuesta cruda con `error_code` distinto de 0 (en cualquier nivel) es un fallo de la cámara."""
    if not isinstance(respuesta, dict):
        return
    codigo = respuesta.get("error_code")
    if codigo not in (None, 0, "0"):
        raise TapoError(f"La cámara ha rechazado la orden (código {codigo}).")
    for v in respuesta.values():
        _comprobar(v)


async def _orden(ip: str, llamada):
    """Orden al motor con tiempo límite; si la cámara no contesta se olvida la conexión (como en `camaras`)."""
    try:
        respuesta = await asyncio.wait_for(llamada, TIMEOUT)
    except TapoError:
        raise
    except Exception as e:  # noqa: BLE001
        _conexiones.pop(ip, None)
        raise TapoError("La cámara no ha respondido.") from e
    _comprobar(respuesta)
    return respuesta


def _parsear_posiciones(datos) -> list:
    """`get_presets()` devuelve listas paralelas (id, name, read_only…) dentro de getPresetConfig.preset.preset."""
    p = datos if isinstance(datos, dict) else {}
    for clave in ("getPresetConfig", "preset", "preset"):
        if isinstance(p, dict) and clave in p:
            p = p[clave]
    if not isinstance(p, dict):
        return []
    ids, nombres, fijas = p.get("id") or [], p.get("name") or [], p.get("read_only") or []
    salida = []
    for i, ident in enumerate(ids):
        nombre = str(nombres[i]).strip() if i < len(nombres) and nombres[i] is not None else ""
        salida.append({"id": str(ident), "nombre": nombre or f"Posición {ident}",
                       "fija": i < len(fijas) and str(fijas[i]) == "1"})
    return salida


async def posiciones(ip: str) -> list:
    """Posiciones guardadas en la cámara: [{id, nombre, fija}]. `fija`: la trae de fábrica y no se puede borrar."""
    _, motor = await _motor(ip)
    return _parsear_posiciones(await _orden(ip, motor.get_presets()))


async def ir_a_posicion(ip: str, ident: str) -> None:
    _, motor = await _motor(ip)
    if not any(p["id"] == str(ident) for p in _parsear_posiciones(await _orden(ip, motor.get_presets()))):
        raise TapoError("Posición no encontrada.")
    try:
        await _orden(ip, motor.goto_preset(str(ident)))
    except TapoError:
        if await _tapada(ip):
            raise TapoError(TAPADA) from None
        raise


async def guardar_posicion(ip: str, nombre: str) -> list:
    """Guarda la posición actual de la cámara con ese nombre y devuelve la lista nueva."""
    nombre = (nombre or "").strip()
    if not 1 <= len(nombre) <= 30:
        raise TapoError("El nombre debe tener entre 1 y 30 caracteres.")
    _, motor = await _motor(ip)
    actuales = _parsear_posiciones(await _orden(ip, motor.get_presets()))
    if len(actuales) >= MAX_POSICIONES:
        raise TapoError(f"Ya hay {MAX_POSICIONES} posiciones guardadas; borra alguna antes.")
    if any(p["nombre"].casefold() == nombre.casefold() for p in actuales):
        raise TapoError("Ya existe una posición con ese nombre.")
    await _orden(ip, motor.save_preset(nombre))
    return _parsear_posiciones(await _orden(ip, motor.get_presets()))


async def borrar_posicion(ip: str, ident: str) -> list:
    """Borra una posición (no las fijas de fábrica) y devuelve la lista nueva. python-kasa no lo trae: orden cruda."""
    dev, motor = await _motor(ip)
    actuales = _parsear_posiciones(await _orden(ip, motor.get_presets()))
    posicion = next((p for p in actuales if p["id"] == str(ident)), None)
    if posicion is None:
        raise TapoError("Posición no encontrada.")
    if posicion["fija"]:
        raise TapoError("Esa posición es fija y no se puede borrar.")
    await _orden(ip, dev._raw_query({"deletePreset": {"preset": {"remove_preset": {"id": [str(ident)]}}}}))
    return _parsear_posiciones(await _orden(ip, motor.get_presets()))


async def cerrar() -> None:
    for dev in list(_conexiones.values()):
        try:
            await dev.disconnect()
        except Exception:  # noqa: BLE001
            pass
    _conexiones.clear()
