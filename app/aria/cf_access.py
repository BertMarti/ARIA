"""Grupo de invitados en Cloudflare Access: añadir y quitar emails al aprobar o revocar un acceso.

La aplicación de ARIA en Access debe tener una política «Allow» que incluya este grupo. Un grupo no puede quedar
vacío, así que siempre lleva una regla de relleno con un email imposible (`RELLENO`). El token solo necesita el
permiso de grupos de Access; nunca se registra.
"""
import asyncio
import logging

import httpx

from . import config

log = logging.getLogger("aria.cf_access")

API = "https://api.cloudflare.com/client/v4"
RELLENO = "nadie@aria.invalid"
_bloqueo = asyncio.Lock()   # leer-cambiar-escribir del grupo, de uno en uno (dos aprobaciones a la vez no se pisan)


class CloudflareError(Exception):
    """Error legible al hablar con Cloudflare."""


def configurado() -> bool:
    return bool(config.CF_API_TOKEN and config.CF_CUENTA and config.CF_GRUPO_INVITADOS)


def _url() -> str:
    return f"{API}/accounts/{config.CF_CUENTA}/access/groups/{config.CF_GRUPO_INVITADOS}"


async def _pedir(metodo: str, **kw) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.request(metodo, _url(), headers={"Authorization": f"Bearer {config.CF_API_TOKEN}"}, **kw)
        j = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise CloudflareError(f"Cloudflare no responde ({type(e).__name__}).") from None
    if not j.get("success"):
        errores = "; ".join(str(e.get("message", "")) for e in j.get("errors", []))[:200]
        raise CloudflareError(f"Cloudflare rechazó el cambio: {errores or r.status_code}.")
    return j.get("result") or {}


def _emails(include: list) -> list[str]:
    return [str(r["email"]["email"]).lower() for r in include if isinstance(r, dict) and isinstance(r.get("email"), dict)]


async def emails() -> list[str]:
    g = await _pedir("GET")
    return [e for e in _emails(g.get("include", [])) if e != RELLENO]


async def _cambiar(email: str, poner: bool) -> bool:
    """True si hubo cambio. Conserva el resto de reglas del grupo tal cual."""
    if not configurado():
        return False
    email = email.strip().lower()
    async with _bloqueo:
        return await _cambiar_bloqueado(email, poner)


async def _cambiar_bloqueado(email: str, poner: bool) -> bool:
    g = await _pedir("GET")
    antes = g.get("include") or []
    if (email in _emails(antes)) == poner:
        return False
    include = [r for r in antes if email not in _emails([r])]
    if poner:
        include.append({"email": {"email": email}})
    if RELLENO not in _emails(include):
        include.append({"email": {"email": RELLENO}})
    await _pedir("PUT", json={"name": g.get("name") or "Invitados ARIA", "include": include,
                              "exclude": g.get("exclude") or [], "require": g.get("require") or []})
    log.info("Grupo de invitados de Cloudflare actualizado (%s un email)", "añadido" if poner else "quitado")
    return True


async def anadir(email: str) -> bool:
    return await _cambiar(email, True)


async def quitar(email: str) -> bool:
    return await _cambiar(email, False)
