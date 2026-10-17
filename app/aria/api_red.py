"""API de Red (/api/red/...) y Seguridad (/api/seguridad/...).

Permisos (permisos.py): el rol `usuario` solo puede `GET /api/red/salud`; todo lo demás es de admin.
"""
import asyncio
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from . import escaneo, estadisticas, premium, red, seguridad, shield, remedios

router = APIRouter()
_acciones = []


def _err(msg: str, estado: int = 400) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=estado)


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


@router.get("/api/red/salud")
async def salud():
    return await red.salud()


@router.get("/api/red/dispositivos")
async def dispositivos():
    try:
        ds = await red.dispositivos()
    except shield.ShieldError as e:
        return _err(str(e), 502)
    return {"dispositivos": ds, "ultimo_escaneo": (await asyncio.to_thread(escaneo.estado))["ultimo"]}


@router.post("/api/red/dispositivos/conocido")
async def marcar(request: Request):
    d = await _json(request)
    clave = d.get("clave")
    conocido = d.get("conocido", True)
    alias = d.get("alias")
    if not isinstance(clave, str) or not clave or not isinstance(conocido, bool) or \
            (alias is not None and not isinstance(alias, str)):
        return _err("Datos no válidos.")
    if not await asyncio.to_thread(red.marcar_conocido, clave, conocido, alias):
        return _err("Dispositivo no encontrado.", 404)
    return {"ok": True}


@router.post("/api/red/dispositivos/conocer-todos")
async def conocer_todos():
    return {"marcados": await asyncio.to_thread(red.conocer_todos)}


@router.post("/api/red/latencia")
async def latencia():
    return await red.latencia()


@router.post("/api/red/velocidad")
async def velocidad():
    try:
        return await red.velocidad()
    except red.RedError as e:
        return _err(str(e), 429 if "cada 10 minutos" in str(e) or "en marcha" in str(e) else 502)


@router.get("/api/red/historial")
async def historial(dias: int = 7):
    return await asyncio.to_thread(red.historial, dias)


@router.get("/api/red/estadisticas")
async def estadisticas_red(horas: int = 24):
    try:
        return {"disponible": True, **await estadisticas.resumen(horas)}
    except estadisticas.EstadisticasError as e:
        if "conectado" in str(e) or "contactar" in str(e):
            # SHIELD-DNS caído o sin configurar: no es un fallo de la petición; la vista lo explica
            return {"disponible": False, "error": str(e), "horas": horas, "dispositivos": [],
                    "totales": {"consultas": 0, "bloqueadas": 0, "porcentaje": 0}}
        return _err(str(e), 400)


@router.get("/api/red/estadisticas/{clave}")
async def estadisticas_dispositivo(clave: str, horas: int = 24):
    try:
        return await estadisticas.detalle(clave, horas)
    except estadisticas.EstadisticasError as e:
        return _err(str(e), 502 if "conectado" in str(e) or "contactar" in str(e) else 404)


@router.get("/api/seguridad/informe")
async def informe():
    return await seguridad.informe()


@router.get("/api/seguridad/escaneo")
async def estado_escaneo():
    return await asyncio.to_thread(escaneo.estado)


@router.post("/api/seguridad/escaneo")
async def escanear(request: Request):
    d = await _json(request)
    perfil = d.get("perfil", "rapido")
    if perfil not in ("rapido", "completo"):
        return _err("Perfil no válido.")
    try:
        return {"id": await asyncio.to_thread(escaneo.solicitar, perfil, d.get("objetivos"), "manual")}
    except escaneo.EscaneoError as e:
        return _err(str(e), 429 if "10 minutos" in str(e) or "pendiente" in str(e) else 400)


async def _hallazgo_actual(clave: str, con_cves=True):
    """El hallazgo vigente con esa clave (primero sin consultar CVE, que es lento; luego con la caché de CVE)."""
    for cves in ((False, True) if con_cves else (False,)):
        inf = await seguridad.informe(con_cves=cves)
        h = next((h for h in inf.get("hallazgos", []) + inf.get("aceptados", []) if h.get("clave") == clave), None)
        if h:
            return h
    return None


def _limitar():
    ahora = time.time()
    _acciones[:] = [x for x in _acciones if ahora - x < 60]
    if len(_acciones) >= 10:
        return False
    _acciones.append(ahora)
    return True


@router.post("/api/seguridad/hallazgos/{clave}/accion", dependencies=[Depends(premium.requiere("remedios"))])
async def accion_hallazgo(clave: str, request: Request):
    if not _limitar():
        return _err("Demasiadas acciones; espera un minuto.", 429)
    d = await _json(request)
    accion = d.get("accion")
    if not isinstance(accion, str):
        return _err("Acción no válida.")
    h = await _hallazgo_actual(clave, True)
    if not h:
        return _err("Hallazgo no encontrado.", 404)
    try:
        texto = await remedios.aplicar(h, accion, request.state.usuario["id"], d)
    except (ValueError, remedios.vpn.VpnError) as e:
        return _err(str(e))
    return {"ok": True, "mensaje": texto}


@router.post("/api/seguridad/hallazgos/{clave}/comprobar")
async def comprobar_hallazgo(clave: str, request: Request):
    if not _limitar():
        return _err("Demasiadas acciones; espera un minuto.", 429)
    h = await _hallazgo_actual(clave, False)
    if not h:
        return _err("Hallazgo no encontrado.", 404)
    try:
        return {"ok": True, "mensaje": await remedios.comprobar(h)}
    except escaneo.EscaneoError as e:
        return _err(str(e), 429)


@router.delete("/api/seguridad/hallazgos/{clave}/estado")
async def reabrir_hallazgo(clave: str):
    if not _limitar():
        return _err("Demasiadas acciones; espera un minuto.", 429)
    if not await asyncio.to_thread(remedios.reabrir, clave):
        return _err("Estado no encontrado.", 404)
    return {"ok": True}
