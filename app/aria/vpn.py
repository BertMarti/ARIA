"""Cliente de la API de wg-easy v15 (HEIMDALL, VPN WireGuard).

Solo se exponen campos de una lista blanca: las claves privadas nunca llegan al navegador.
"""
import re
from datetime import datetime, timezone

import httpx

from . import config

NOMBRE_RE = re.compile(r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ ._-]{1,32}$")
CONECTADO_SEG = 180  # handshake reciente = conectado


class VpnError(Exception):
    """Error legible (en español)."""


def configurado() -> bool:
    return bool(config.VPN_URL and config.VPN_USER and config.VPN_PASSWORD)


def panel_url() -> str:
    return config.VPN_URL.rstrip("/")


def nombre_valido(nombre) -> bool:
    return isinstance(nombre, str) and bool(NOMBRE_RE.fullmatch(nombre.strip())) and bool(nombre.strip())


def _conectado(handshake: str | None, ahora: datetime | None = None) -> bool:
    if not handshake:
        return False
    try:
        t = datetime.fromisoformat(handshake.replace("Z", "+00:00"))
    except ValueError:
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return ((ahora or datetime.now(timezone.utc)) - t).total_seconds() < CONECTADO_SEG


def limpiar_cliente(c: dict) -> dict:
    hs = c.get("latestHandshakeAt")
    return {
        "id": c.get("id"),
        "nombre": c.get("name"),
        "activo": bool(c.get("enabled")),
        "ip": c.get("ipv4Address"),
        "ultimo_handshake": hs,
        "conectado": _conectado(hs),
        "recibido": c.get("transferRx") or 0,
        "enviado": c.get("transferTx") or 0,
        "creado": c.get("createdAt"),
        "caduca": c.get("expiresAt"),
    }


async def _llamar(metodo: str, ruta: str, **kw) -> httpx.Response:
    if not configurado():
        raise VpnError("HEIMDALL no está conectado.")
    try:
        # Certificado autofirmado accedido por IP: no se puede verificar.
        async with httpx.AsyncClient(timeout=10, verify=False, auth=(config.VPN_USER, config.VPN_PASSWORD)) as c:
            r = await c.request(metodo, config.VPN_URL.rstrip("/") + ruta, **kw)
    except httpx.HTTPError:
        raise VpnError("No se pudo contactar con HEIMDALL.") from None
    if r.status_code == 401:
        raise VpnError("HEIMDALL rechazó el usuario o la contraseña (revisa VPN_USER y VPN_PASSWORD en .env).")
    if r.status_code == 404:
        raise VpnError("Dispositivo no encontrado en HEIMDALL.")
    if r.status_code >= 400:
        raise VpnError(f"HEIMDALL devolvió un error ({r.status_code}).")
    return r


def _id(cid) -> int:
    try:
        n = int(cid)
    except (TypeError, ValueError):
        raise VpnError("Identificador no válido.") from None
    if n < 0:
        raise VpnError("Identificador no válido.")
    return n


async def listar() -> list:
    r = await _llamar("GET", "/api/client")
    try:
        datos = r.json()
    except ValueError:
        raise VpnError("Respuesta no válida de HEIMDALL.") from None
    return [limpiar_cliente(c) for c in datos if isinstance(c, dict)]


async def crear(nombre: str) -> int:
    if not nombre_valido(nombre):
        raise VpnError("Nombre no válido: usa letras, números, espacios y - _ . (máximo 32).")
    r = await _llamar("POST", "/api/client", json={"name": nombre.strip(), "expiresAt": None})
    try:
        return int(r.json()["clientId"])
    except (ValueError, KeyError, TypeError):
        raise VpnError("HEIMDALL no devolvió el identificador del dispositivo.") from None


async def qr(cid) -> bytes:
    return (await _llamar("GET", f"/api/client/{_id(cid)}/qrcode.svg")).content


async def configuracion(cid) -> bytes:
    return (await _llamar("GET", f"/api/client/{_id(cid)}/configuration")).content


async def activar(cid, activo: bool) -> None:
    await _llamar("POST", f"/api/client/{_id(cid)}/{'enable' if activo else 'disable'}")


async def eliminar(cid) -> None:
    await _llamar("DELETE", f"/api/client/{_id(cid)}")
