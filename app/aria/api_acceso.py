"""Acceso por invitación: la página pública /acceso (pedir acceso y ver el estado) y su gestión (administradores).

/acceso, /acceso/solicitar y /acceso/estado/<token> son públicas (sin sesión): no devuelven nada de nadie más que
el estado de la propia solicitud. Todo lo de /api/acceso es solo para administradores (permisos.py deniega por
defecto al rol `usuario`).
"""
import asyncio
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import cf_access, config, invitados, usuarios

log = logging.getLogger("aria.acceso")
router = APIRouter()

TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_tareas: set = set()


def ip_cliente(request: Request) -> str:
    """IP real del visitante: detrás de Cloudflare llega en CF-Connecting-IP (Caddy no la reescribe)."""
    return (request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "") or "?")[:64]


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _err(texto: str, estado: int = 400) -> JSONResponse:
    return JSONResponse({"error": texto}, status_code=estado)


async def _turnstile_ok(respuesta: str, ip: str) -> bool:
    if not config.TURNSTILE_SECRETO:
        return True
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(TURNSTILE_URL, data={"secret": config.TURNSTILE_SECRETO, "response": respuesta or "", "remoteip": ip})
        return bool(r.json().get("success"))
    except (httpx.HTTPError, ValueError):
        log.warning("Turnstile no responde: se rechaza la solicitud por prudencia")
        return False


def _en_segundo_plano(coro) -> None:
    t = asyncio.create_task(coro)
    _tareas.add(t)
    t.add_done_callback(_tareas.discard)


# --- Público --------------------------------------------------------------------------------------------------------
@router.get("/acceso/config")
async def acceso_config():
    """Lo que la página necesita saber: si hay Turnstile (y su clave pública)."""
    return {"turnstile": config.TURNSTILE_SITIO or None}


@router.post("/acceso/solicitar")
async def acceso_solicitar(request: Request):
    d = await _json(request)
    if d.get("web"):   # campo trampa: invisible para personas, los bots lo rellenan
        return {"ok": True, "token": None}
    ip = ip_cliente(request)
    if not await _turnstile_ok(str(d.get("turnstile") or ""), ip):
        return _err("No hemos podido comprobar que eres una persona. Recarga la página y vuelve a intentarlo.")
    try:
        r = await asyncio.to_thread(invitados.solicitar, d.get("nombre"), d.get("email"), d.get("motivo"), ip)
    except invitados.AccesoError as e:
        return _err(str(e), 429 if "Prueba" in str(e) else 400)
    if not r["repetida"]:
        from . import telegram
        _en_segundo_plano(telegram.avisar_solicitud(r["id"]))
    return {"ok": True, "token": r["token"]}


@router.get("/acceso/estado/{token}")
async def acceso_estado(token: str):
    e = await asyncio.to_thread(invitados.estado_publico, token)
    return e or _err("No encuentro esa solicitud.", 404)


# --- Administración (solo admin) ------------------------------------------------------------------------------------
async def aprobar(sid: int, perfil: str, limites: dict | None, admin_id: int | None) -> dict:
    """Aprueba en ARIA y, si se puede, añade el email al grupo de Cloudflare. Devuelve también si hay paso manual."""
    r = await asyncio.to_thread(invitados.aprobar, sid, perfil, limites, admin_id)
    cf = await _cf("anadir", r["usuario"]["email"])
    return {**r, "cloudflare": cf}


async def revocar(uid: int) -> dict:
    u = await asyncio.to_thread(invitados.revocar, uid)
    return {"usuario": u, "cloudflare": await _cf("quitar", u["email"])}


async def _cf(op: str, email: str) -> str:
    """«hecho», «manual» (sin token configurado) o el error de Cloudflare."""
    if not cf_access.configurado():
        return "manual"
    try:
        await (cf_access.anadir(email) if op == "anadir" else cf_access.quitar(email))
        return "hecho"
    except cf_access.CloudflareError as e:
        log.warning("Cloudflare: %s", e)
        return str(e)


async def caducar_vencidos() -> list:
    """Desactiva los accesos caducados y los saca de Cloudflare (lo llama el bucle de avisos)."""
    hechos = []
    for v in await asyncio.to_thread(invitados.vencidos):
        try:
            await revocar(v["user_id"])
            hechos.append(v["user_id"])
        except invitados.AccesoError:
            continue
    return hechos


@router.get("/api/acceso")
async def api_acceso():
    return {"pendientes": await asyncio.to_thread(invitados.pendientes), "invitados": await asyncio.to_thread(invitados.listar),
            "perfiles": invitados.PERFILES, "secciones": invitados.SECCIONES, "cloudflare": cf_access.configurado()}


@router.post("/api/acceso/solicitudes/{sid:int}/aprobar")
async def api_aprobar(request: Request, sid: int):
    d = await _json(request)
    try:
        return await aprobar(sid, str(d.get("perfil") or invitados.PERFIL_DEFECTO), d.get("limites"), request.state.usuario["id"])
    except (invitados.AccesoError, usuarios.UsuarioError) as e:
        return _err(str(e))


@router.post("/api/acceso/solicitudes/{sid:int}/rechazar")
async def api_rechazar(sid: int):
    try:
        return {"solicitud": await asyncio.to_thread(invitados.rechazar, sid)}
    except invitados.AccesoError as e:
        return _err(str(e))


@router.patch("/api/acceso/invitados/{uid:int}")
async def api_cambiar(request: Request, uid: int):
    """Cambia perfil, límites o días de acceso (y, si estaba revocado o caducado, lo reactiva)."""
    d = await _json(request)
    if not await asyncio.to_thread(invitados.de, uid):
        return _err("Ese usuario no es un invitado.", 404)
    perfil = str(d.get("perfil") or invitados.de(uid)["perfil"])
    if perfil not in invitados.PERFILES:
        return _err("Perfil desconocido.")
    dias = d.get("dias") if isinstance(d.get("dias"), int) and not isinstance(d.get("dias"), bool) and 0 <= d["dias"] <= 365 else None
    lim = await asyncio.to_thread(invitados.fijar, uid, perfil, d.get("limites"), request.state.usuario["id"], dias)
    cf = None
    u = usuarios.por_id(uid)
    if d.get("reactivar") and u and not u["activo"]:
        await asyncio.to_thread(usuarios.actualizar, uid, None, True)
        cf = await _cf("anadir", u["email"])
    return {"limites": invitados.publico(lim), "cloudflare": cf}


@router.post("/api/acceso/invitados/{uid:int}/revocar")
async def api_revocar(uid: int):
    try:
        return await revocar(uid)
    except invitados.AccesoError as e:
        return _err(str(e), 404)
