"""Inicio de sesión único con Cloudflare Access.

Se VERIFICA el JWT que Cloudflare añade en `Cf-Access-Jwt-Assertion` (firma RS256 con las
claves públicas de https://<equipo>/cdn-cgi/access/certs, `aud`, `iss`, caducidad y `email`).
La cabecera `Cf-Access-Authenticated-User-Email` nunca se usa: cualquiera puede falsificarla.
"""
import asyncio
import logging
import time

import httpx
import jwt
from jwt import PyJWK

from . import config

log = logging.getLogger("aria.sso")

CABECERA = "cf-access-jwt-assertion"
CACHE_S = 3600          # vida de las claves en caché
ESPERA_REFETCH_S = 30   # mínimo entre descargas (evita que un `kid` inventado nos haga martillear a Cloudflare)
MARGEN_S = 30           # tolerancia de reloj para exp / nbf / iat

OK, INVALIDO, TRANSITORIO = "ok", "invalido", "transitorio"

_claves: dict = {}       # kid -> clave pública
_descargada = 0.0        # cuándo se cargó la caché
_intento = 0.0           # último intento de descarga (con éxito o sin él)
_cerrojo = asyncio.Lock()


def habilitado() -> bool:
    return bool(config.CF_TEAM and config.CF_AUD)


def emisor() -> str:
    return f"https://{config.CF_TEAM}"


def url_salida() -> str:
    return f"{emisor()}/cdn-cgi/access/logout"


async def _descargar_jwks() -> dict:
    """Devuelve el JSON de claves de Cloudflare (las pruebas lo sustituyen)."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5, connect=3)) as c:
        r = await c.get(f"{emisor()}/cdn-cgi/access/certs")
        r.raise_for_status()
        return r.json()


async def _refrescar() -> bool:
    global _claves, _descargada, _intento
    _intento = time.monotonic()
    try:
        datos = await _descargar_jwks()
        nuevas = {}
        for k in datos.get("keys", []):
            if isinstance(k, dict) and k.get("kid") and k.get("kty") == "RSA":
                nuevas[k["kid"]] = PyJWK(k).key
    except Exception as e:  # noqa: BLE001 - red, JSON o claves mal formadas: se reintentará
        log.warning("No se pudieron obtener las claves de Cloudflare Access: %s", type(e).__name__)
        return False
    if not nuevas:
        return False
    _claves, _descargada = nuevas, time.monotonic()
    return True


async def _clave(kid: str):
    """Clave pública para `kid`; refresca la caché si caducó o si el `kid` no se conoce."""
    ahora = time.monotonic()
    caducada = ahora - _descargada > CACHE_S
    if kid in _claves and not caducada:
        return _claves[kid], True
    async with _cerrojo:
        if kid in _claves and time.monotonic() - _descargada <= CACHE_S:
            return _claves[kid], True
        if time.monotonic() - _intento >= ESPERA_REFETCH_S or not _claves:
            if not await _refrescar() and not _claves:
                return None, False          # sin claves: fallo transitorio
        return _claves.get(kid), True


async def identificar(token: str | None) -> tuple[str, str | None]:
    """(estado, email). estado: ok | invalido | transitorio (no se pudo contactar con Cloudflare)."""
    if not habilitado() or not token or len(token) > 8192:
        return INVALIDO, None
    try:
        cab = jwt.get_unverified_header(token)
        kid = cab.get("kid")
        if cab.get("alg") != "RS256" or not isinstance(kid, str):
            return INVALIDO, None
        clave, red_ok = await _clave(kid)
        if clave is None:
            return (INVALIDO if red_ok else TRANSITORIO), None
        datos = jwt.decode(token, clave, algorithms=["RS256"], audience=config.CF_AUD,
                           issuer=emisor(), leeway=MARGEN_S,
                           options={"require": ["exp", "iat", "aud", "iss"]})
    except jwt.PyJWTError:
        return INVALIDO, None
    email = datos.get("email")
    if not isinstance(email, str) or "@" not in email or len(email) > 254:
        return INVALIDO, None   # p. ej. un token de servicio: no es una persona
    return OK, email.strip().lower()
