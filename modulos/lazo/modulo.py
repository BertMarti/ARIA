"""Módulo «Lazo»: tu servidor de Lazo (https://github.com/BertMarti/lazo) dentro de ARIA.

Lazo corre en su propio Compose (carpeta del repositorio de Lazo) y se publica por el túnel de Cloudflare del
homelab. Este módulo solo pone:
- el mosaico de Inicio (`/api/modulos/lazo/abrir`, con sesión), que lleva a `LAZO_URL`;
- un chequeo «caido» que avisa al administrador si Lazo deja de responder. Pregunta por la red interna
  (`LAZO_INTERNA`, por defecto http://lazo-caddy:80, con el Host público para que Caddy lo atienda), así un bloqueo
  de las IP de Cloudflare no da una falsa alarma.

Configuración (.env de ARIA): `LAZO_URL` (la dirección pública, https://lazo.tu-dominio) y, si hace falta,
`LAZO_INTERNA`. Para que ARIA llegue a lazo-caddy, aria-app tiene que estar en la red «lazo_tunel» (ver README).
"""
from urllib.parse import urlsplit

import httpx
from fastapi.responses import RedirectResponse

_SIN_CACHE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _base(url, nombre: str, esquemas=("https",)) -> str:
    url = (url or "").strip().rstrip("/")
    p = urlsplit(url)
    if p.scheme not in esquemas or not p.hostname or p.username or p.password or p.path not in ("", "/"):
        raise ValueError(f"{nombre} debe ser una dirección {'/'.join(esquemas)} sin usuario, contraseña ni ruta")
    return url


def registrar(aria):
    publica = _base(aria.config("LAZO_URL"), "LAZO_URL")
    interna = _base(aria.config("LAZO_INTERNA") or "http://lazo-caddy:80", "LAZO_INTERNA", ("http", "https"))
    host_publico = urlsplit(publica).hostname

    r = aria.router(usuario=[("GET", "/abrir")])

    @r.get("/abrir")
    async def abrir():
        """Mosaico de Inicio: siempre a la dirección pública de Lazo (la que usa también la app del móvil)."""
        return RedirectResponse(f"{publica}/", status_code=303, headers=_SIN_CACHE)

    @aria.chequeo("caido", intervalo_min=5, severidad="aviso", confirmaciones=2, texto_ok="Lazo vuelve a responder.")
    async def caido():
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as cli:
                res = await cli.get(f"{interna}/api/health", headers={"Host": host_publico})
            ok = res.status_code == 200
        except httpx.HTTPError:
            ok = False
        return [] if ok else [aria.Problema("lazo", "Lazo no responde: tu familia no puede entrar en sus grupos.")]
