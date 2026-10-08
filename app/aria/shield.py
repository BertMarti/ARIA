"""Cliente de la API de Pi-hole v6 (SHIELD-DNS).

Pi-hole limita las sesiones de API simultáneas: se guarda UN solo sid en memoria,
se reutiliza y solo se vuelve a autenticar ante un 401. Al apagar la app se cierra.
"""
import asyncio
from urllib.parse import quote

import httpx

from . import config


class ShieldError(Exception):
    """Error legible (en español) para la interfaz o el modelo."""


_sid: str | None = None
_lock = asyncio.Lock()


def configurado() -> bool:
    return bool(config.SHIELD_URL and config.SHIELD_PASSWORD)


def panel_url() -> str:
    return config.SHIELD_URL.rstrip("/") + "/admin"


async def _autenticar(c: httpx.AsyncClient) -> str:
    global _sid
    r = await c.post(f"{config.SHIELD_URL}/api/auth", json={"password": config.SHIELD_PASSWORD})
    if r.status_code in (401, 403):
        raise ShieldError("SHIELD-DNS rechazó la contraseña (revisa SHIELD_PASSWORD en .env).")
    if r.status_code == 429:
        raise ShieldError("SHIELD-DNS tiene demasiadas sesiones abiertas. Reintenta en un momento.")
    if r.status_code != 200:
        raise ShieldError(f"SHIELD-DNS devolvió un error ({r.status_code}).")
    sid = (r.json().get("session") or {}).get("sid")
    if not sid:
        raise ShieldError("SHIELD-DNS no devolvió una sesión válida.")
    _sid = sid
    return sid


async def _llamar(metodo: str, ruta: str, **kw) -> dict:
    if not configurado():
        raise ShieldError("SHIELD-DNS no está conectado.")
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            async with _lock:
                sid = _sid or await _autenticar(c)
            for intento in (0, 1):
                r = await c.request(metodo, config.SHIELD_URL + ruta, headers={"X-FTL-SID": sid}, **kw)
                if r.status_code == 401 and intento == 0:
                    async with _lock:
                        sid = await _autenticar(c)
                    continue
                break
    except httpx.HTTPError:
        raise ShieldError("No se pudo contactar con SHIELD-DNS.") from None
    if r.status_code >= 400:
        raise ShieldError(f"SHIELD-DNS devolvió un error ({r.status_code}).")
    try:
        return r.json() if r.content else {}
    except ValueError:
        return {}


async def cerrar() -> None:
    """Cierra la sesión (se llama al apagar la app)."""
    global _sid
    if not _sid:
        return
    try:
        async with httpx.AsyncClient(timeout=4) as c:
            await c.delete(f"{config.SHIELD_URL}/api/auth", headers={"X-FTL-SID": _sid})
    except httpx.HTTPError:
        pass
    _sid = None


async def bloqueo() -> dict:
    j = await _llamar("GET", "/api/dns/blocking")
    return {"activo": j.get("blocking") == "enabled", "temporizador": j.get("timer")}


async def resumen() -> dict:
    s, b, top = await asyncio.gather(
        _llamar("GET", "/api/stats/summary"),
        bloqueo(),
        _llamar("GET", "/api/stats/top_domains", params={"blocked": "true", "count": 5}),
    )
    q = s.get("queries") or {}
    return {
        "consultas": q.get("total", 0),
        "bloqueadas": q.get("blocked", 0),
        "porcentaje": round(float(q.get("percent_blocked") or 0), 1),
        "dominios_unicos": q.get("unique_domains", 0),
        "clientes": (s.get("clients") or {}).get("active", 0),
        "lista_negra": (s.get("gravity") or {}).get("domains_being_blocked", 0),
        "bloqueo_activo": b["activo"],
        "temporizador": b["temporizador"],
        "top_bloqueados": [{"dominio": d.get("domain", ""), "cuenta": d.get("count", 0)}
                           for d in (top.get("domains") or [])][:5],
        "panel": panel_url(),
    }


async def pausar(minutos: int) -> dict:
    if not 1 <= minutos <= 120:
        raise ShieldError("La pausa debe durar entre 1 y 120 minutos.")
    await _llamar("POST", "/api/dns/blocking", json={"blocking": False, "timer": minutos * 60})
    return await bloqueo()


async def reanudar() -> dict:
    await _llamar("POST", "/api/dns/blocking", json={"blocking": True})
    return await bloqueo()


async def resumen_dia(desde: float, hasta: float) -> dict | None:
    """Consultas y bloqueos de un intervalo (base de datos de Pi-hole). None si no hay datos de ese día."""
    j = await _llamar("GET", "/api/stats/database/summary", params={"from": int(desde), "until": int(hasta)})
    total = int(j.get("sum_queries") or 0)
    if total <= 0:
        return None
    bloqueadas = int(j.get("sum_blocked") or 0)
    return {"consultas": total, "bloqueadas": bloqueadas, "porcentaje": round(bloqueadas * 100 / total, 1)}


# --- Grupos, clientes y dominios (control parental, ver control.py) -----------------------------------------
# Pi-hole v6: /api/groups, /api/clients y /api/domains/deny/regex. Los clientes se identifican por IP y un
# cliente listado solo pertenece a los grupos que se le indiquen (hay que incluir el 0 = Default para que
# conserve las listas de anuncios). Los identificadores van codificados en la ruta (`.*` -> `.%2A`).
def _ruta(x: str) -> str:
    return quote(x, safe="")


async def grupos() -> list:
    return (await _llamar("GET", "/api/groups")).get("groups") or []


async def crear_grupo(nombre: str, comentario: str = "") -> dict:
    j = await _llamar("POST", "/api/groups", json={"name": nombre, "comment": comentario, "enabled": True})
    return (j.get("groups") or [{}])[0]


async def clientes() -> list:
    return (await _llamar("GET", "/api/clients")).get("clients") or []


async def crear_cliente(ip: str, grupos_: list, comentario: str) -> dict:
    j = await _llamar("POST", "/api/clients", json={"client": ip, "comment": comentario, "groups": grupos_})
    return (j.get("clients") or [{}])[0]


async def actualizar_cliente(ip: str, grupos_: list, comentario: str) -> dict:
    j = await _llamar("PUT", f"/api/clients/{_ruta(ip)}", json={"comment": comentario, "groups": grupos_})
    return (j.get("clients") or [{}])[0]


async def borrar_cliente(ip: str) -> None:
    await _llamar("DELETE", f"/api/clients/{_ruta(ip)}")


async def dominios_regex_deny() -> list:
    return (await _llamar("GET", "/api/domains/deny/regex")).get("domains") or []


async def crear_dominio_regex_deny(regex: str, grupos_: list, comentario: str, activo: bool) -> dict:
    j = await _llamar("POST", "/api/domains/deny/regex",
                      json={"domain": regex, "comment": comentario, "groups": grupos_, "enabled": activo})
    return (j.get("domains") or [{}])[0]


async def actualizar_dominio_regex_deny(regex: str, grupos_: list, comentario: str, activo: bool) -> dict:
    j = await _llamar("PUT", f"/api/domains/deny/regex/{_ruta(regex)}",
                      json={"comment": comentario, "groups": grupos_, "enabled": activo})
    return (j.get("domains") or [{}])[0]


async def borrar_dominio_regex_deny(regex: str) -> None:
    await _llamar("DELETE", f"/api/domains/deny/regex/{_ruta(regex)}")
