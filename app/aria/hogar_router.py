"""Router TP-Link (la misma interfaz que usa la app Tether) con `tplinkrouterc6u`.

El router solo admite una sesión de administración: cada consulta inicia sesión y la cierra en `finally` (si no, echa
a la app Tether), y un candado impide dos sesiones a la vez. El estado se guarda 60 s para no iniciar sesión a menudo.
"""
import asyncio
import time

from . import config

_candado = asyncio.Lock()
_cache = {"cuando": 0.0, "estado": None}
TIMEOUT = 8


class RouterError(Exception):
    pass


def configurado() -> bool:
    return bool(config.ROUTER_PASSWORD)


def _sesion(operacion):
    """Inicia sesión, ejecuta y cierra SIEMPRE la sesión. Corre en un hilo (la librería es síncrona)."""
    from tplinkrouterc6u import TplinkRouterProvider
    cliente = TplinkRouterProvider.get_client(f"http://{config.ROUTER_IP}", config.ROUTER_PASSWORD, timeout=TIMEOUT)
    try:
        cliente.authorize()
        return operacion(cliente)
    finally:
        try:
            cliente.logout()
        except Exception:  # noqa: BLE001 - si el cierre falla, el router caduca la sesión solo
            pass


async def _usar(operacion):
    if not configurado():
        raise RouterError("El router no está configurado.")
    async with _candado:
        try:
            return await asyncio.wait_for(asyncio.to_thread(_sesion, operacion), TIMEOUT * 3)
        except RouterError:
            raise
        except Exception as e:  # noqa: BLE001 - nunca se devuelve la traza (podría llevar datos de la sesión)
            raise RouterError("No se pudo hablar con el router.") from e


def _mac(mac) -> str:
    partes = str(mac or "").replace("-", ":").split(":")
    return ":".join(partes[-3:]).upper() if len(partes) >= 3 else ""


def _banda(tipo) -> str:
    nombre = getattr(tipo, "name", str(tipo or ""))
    if nombre == "WIRED":
        return "cable"
    if "GUEST" in nombre:
        return "invitados"
    for clave, texto in (("2G", "2,4 GHz"), ("5G", "5 GHz"), ("6G", "6 GHz")):
        if clave in nombre:
            return texto
    return ""


async def estado() -> dict:
    if _cache["estado"] is not None and time.monotonic() - _cache["cuando"] < 60:
        return _cache["estado"]

    def leer(c):
        estado_ = c.get_status()
        try:
            modelo = c.get_firmware().model
        except Exception:  # noqa: BLE001 - no todos los modelos lo dan
            modelo = "TP-Link"
        return estado_, modelo

    s, modelo = await _usar(leer)
    clientes = [{"nombre": getattr(d, "hostname", "") or "Dispositivo", "mac": _mac(getattr(d, "macaddress", "")),
                 "ip": str(getattr(d, "ipaddress", "") or ""), "banda": _banda(getattr(d, "type", None))}
                for d in (getattr(s, "devices", None) or []) if getattr(d, "active", True)]
    d = {"modelo": modelo, "conectados": getattr(s, "clients_total", None) or len(clientes),
         "clientes": sorted(clientes, key=lambda x: x["nombre"].lower())}
    for atributo, clave in (("guest_2g_enable", "invitados_24"), ("guest_5g_enable", "invitados_5")):
        valor = getattr(s, atributo, None)
        if valor is not None:
            d[clave] = bool(valor)
    _cache.update(cuando=time.monotonic(), estado=d)
    return d


async def invitados(activa: bool) -> dict:
    def cambiar(c):
        from tplinkrouterc6u import Connection
        for banda in (Connection.GUEST_2G, Connection.GUEST_5G):
            c.set_wifi(banda, bool(activa))
    await _usar(cambiar)
    _cache["cuando"] = 0.0
    return {"activa": bool(activa)}


async def reiniciar() -> dict:
    await _usar(lambda c: c.reboot())
    _cache["cuando"] = 0.0
    return {"ok": True}
