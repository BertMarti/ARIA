"""Cliente mínimo de la API oficial de Govee, sin bloquear el bucle asyncio."""
import asyncio
import time
import uuid

import httpx

from . import config

BASE = "https://openapi.api.govee.com/router/api/v1/"
_cache = {"cuando": 0.0, "dispositivos": []}
_ultimo = {}


class GoveeError(Exception):
    pass


def configurado():
    return bool(config.GOVEE_API_KEY)


def _estado(capacidades: list, instancia: str, defecto=None):
    """Valor de una capacidad en la respuesta de device/state: [{type, instance, state: {value}}]."""
    for c in capacidades or []:
        if c.get("instance") == instancia:
            return (c.get("state") or {}).get("value", defecto)
    return defecto


async def _peticion(metodo, ruta, json=None):
    if not configurado():
        raise GoveeError("Govee no está configurado.")
    espera = max(0, 1 - (time.monotonic() - _ultimo.get(ruta, 0)))
    if espera:
        await asyncio.sleep(espera)
    cab = {"Govee-API-Key": config.GOVEE_API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=BASE, timeout=8) as cliente:
        for intento in range(2):
            try:
                r = await cliente.request(metodo, ruta, headers=cab, json=json)
            except (httpx.HTTPError, TimeoutError) as e:
                raise GoveeError("Govee no responde.") from e
            _ultimo[ruta] = time.monotonic()
            if r.status_code == 429 and intento == 0:
                await asyncio.sleep(1)
                continue
            if r.is_error:
                raise GoveeError("Govee no responde correctamente.")
            d = r.json()
            # La API v2 responde {"code": 200, "message"/"msg", "data" (lista) o "payload" (estado/control)}.
            if str(d.get("code", 200)) != "200":
                raise GoveeError("Govee ha rechazado la petición.")
            return d.get("data") if "data" in d else d.get("payload", d)
    raise GoveeError("Govee no responde correctamente.")


async def _listar_bruto():
    ahora = time.monotonic()
    if ahora - _cache["cuando"] < 600:
        return _cache["dispositivos"]
    d = await _peticion("GET", "user/devices")
    filas = d if isinstance(d, list) else d.get("devices", [])
    _cache.update(cuando=ahora, dispositivos=filas)
    return filas


async def luces():
    filas = await _listar_bruto()
    salida = []
    for d in filas:
        estado = {}
        try:
            estado = await _peticion("POST", "device/state", {"requestId": str(uuid.uuid4()), "payload": {"sku": d.get("sku"), "device": d.get("device")}})
        except GoveeError:
            estado = {}
        caps = estado.get("capabilities", []) if isinstance(estado, dict) else []
        color = _estado(caps, "colorRgb")
        salida.append({"nombre": (d.get("deviceName") or "").strip() or "Luz", "id": d.get("device"), "sku": d.get("sku"),
                       "encendida": _estado(caps, "powerSwitch", 0) in (1, True, "on"),
                       "brillo": _estado(caps, "brightness"),
                       "color": f"#{int(color):06x}" if isinstance(color, int) and 0 <= color <= 0xFFFFFF else None,
                       "en_linea": _estado(caps, "online", True) not in (False, "false")})
    return salida


async def cambiar(identificador, encendida=None, brillo=None, color=None):
    if not any(x is not None for x in (encendida, brillo, color)):
        raise GoveeError("No hay ningún cambio.")
    device = next((d for d in await _listar_bruto() if d.get("device") == identificador), None)
    if not device:
        raise GoveeError("Luz no encontrada.")
    comandos = []
    if encendida is not None: comandos.append({"name": "powerSwitch", "value": 1 if encendida else 0})
    if brillo is not None: comandos.append({"name": "brightness", "value": brillo})
    if color is not None: comandos.append({"name": "colorRgb", "value": color})
    for comando in comandos:
        await _peticion("POST", "device/control", {"requestId": str(uuid.uuid4()), "payload": {"sku": device.get("sku"), "device": identificador, "capability": {"type": "devices.capabilities." + ("on_off" if comando["name"] == "powerSwitch" else "range" if comando["name"] == "brightness" else "color_setting"), "instance": comando["name"], "value": comando["value"]}}})
    return {"ok": True}   # la pantalla ya muestra el cambio; pedir el estado de todas gastaría cupo de la API
