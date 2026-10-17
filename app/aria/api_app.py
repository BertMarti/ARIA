"""API de vinculación y resumen de la aplicación nativa."""
import asyncio
import hashlib
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from . import agenda, avisos, briefing, dispositivos_app, invitados, premium, ubicacion

router = APIRouter()
_lim_crear = avisos.Limitador(5, 3600)
_lim_resumen = avisos.Limitador(60, 3600)


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


@router.post("/api/app/dispositivos")
async def crear(request: Request):
    u = request.state.usuario
    if getattr(request.state, "vista", None) or await asyncio.to_thread(invitados.de, u["id"]):
        return JSONResponse({"error": "Esta cuenta no puede vincular dispositivos."}, status_code=403)
    if not _lim_crear.permitir(u["id"]):
        return JSONResponse({"error": "Demasiadas peticiones seguidas; espera un poco."}, status_code=429)
    d = await _json(request)
    if not isinstance(d.get("nombre", ""), str) or not d.get("nombre", "").strip() or len(d["nombre"].strip()) > 60:
        return JSONResponse({"error": "El nombre debe tener entre 1 y 60 caracteres."}, status_code=400)
    # ARIA Gratis: un móvil vinculado (avisos y widget); Premium: los que quieras, también el token de Atajos/Siri.
    if not premium.tiene("app_extra") and len(await asyncio.to_thread(dispositivos_app.listar, u["id"])) >= 1:
        return JSONResponse({"error": "Con ARIA Gratis puedes vincular un móvil. Hazte Premium para tener más.",
                             "premium": "app_extra"}, status_code=402)
    return await asyncio.to_thread(dispositivos_app.crear, u["id"], d["nombre"])


@router.get("/api/app/dispositivos")
async def listar(request: Request):
    return {"dispositivos": await asyncio.to_thread(dispositivos_app.listar, request.state.usuario["id"])}


@router.delete("/api/app/dispositivos/{ident:int}")
async def revocar(ident: int, request: Request):
    ok = await asyncio.to_thread(dispositivos_app.revocar, request.state.usuario["id"], ident)
    return {"ok": ok} if ok else JSONResponse({"error": "Dispositivo no encontrado."}, status_code=404)


@router.get("/api/app/resumen")
async def resumen(request: Request):
    u = request.state.usuario
    token = request.state.app_token
    if not _lim_resumen.permitir(hashlib.sha256(token.encode()).hexdigest()):
        return JSONResponse({"error": "Demasiadas peticiones seguidas; espera un poco."}, status_code=429)
    datos = await _datos_resumen(u)
    if request.query_params.get("formato") == "texto":
        return PlainTextResponse(_texto_resumen(datos), media_type="text/plain; charset=utf-8")
    return datos


async def _datos_resumen(u: dict) -> dict:
    lim = await asyncio.to_thread(invitados.de, u["id"]) if u["rol"] != "admin" else None
    avisos_d = await asyncio.to_thread(avisos.listar, u["id"], 100)
    ahora = time.time()
    pendientes = [{"id": a["id"], "texto": a["texto"][:300], "severidad": a["severidad"], "ts": a["creado"]}
                  for a in avisos_d["avisos"] if not a["leido"]][:20]
    # El tiempo es el de casa (lleva el nombre del pueblo): un invitado solo lo ve si su acceso incluye Inicio.
    lugar = ubicacion._casa()
    tiempo_d = await briefing._tiempo(lugar) if lim is None or "inicio" in lim["secciones"] else None
    tiempo_mini = None if not tiempo_d else {"lugar": tiempo_d.get("ciudad"), "actual": tiempo_d.get("actual"),
                                             "min": tiempo_d.get("min"), "max": tiempo_d.get("max"),
                                             "cielo": tiempo_d.get("cielo")}
    proximo = None
    if lim is None or "agenda" in lim["secciones"]:
        desde = briefing.tiempo.ahora()
        eventos = await asyncio.to_thread(agenda.listar_eventos, u["id"], desde.isoformat(),
                                          (desde + timedelta(days=7)).isoformat())
        futuro = [e for e in eventos if e.get("inicio", "") >= desde.isoformat()]
        if futuro:
            proximo = {"titulo": futuro[0].get("titulo"), "inicio": futuro[0].get("inicio")}
    return {"avisos": pendientes, "tiempo": tiempo_mini, "proximo": proximo, "generado": ahora}


def _texto_resumen(datos: dict) -> str:
    partes = []
    pendientes = datos["avisos"]
    if pendientes:
        primero = pendientes[0]["texto"].replace("\n", " ").strip()[:120]
        if len(pendientes[0]["texto"].replace("\n", " ").strip()) > 120:
            primero += "…"
        unidad = "aviso" if len(pendientes) == 1 else "avisos"
        partes.append(f"Tienes {len(pendientes)} {unidad} sin leer: {primero}{'' if primero.endswith(('.', '!', '?', '…')) else '.'}")
    tiempo_d = datos.get("tiempo")
    if tiempo_d:
        cielo = tiempo_d.get("cielo") or "sin descripción"
        partes.append(f"En {tiempo_d.get('lugar') or 'casa'} hace {tiempo_d.get('actual')} grados, {cielo}; máxima de {tiempo_d.get('max')}.")
    proximo = datos.get("proximo")
    if proximo:
        inicio = datetime.fromisoformat(proximo["inicio"].replace("Z", "+00:00")).astimezone(briefing.tiempo.zona())
        ahora = briefing.tiempo.ahora()
        dias = (inicio.date() - ahora.date()).days
        cuando = "hoy" if dias == 0 else "mañana" if dias == 1 else f"el {briefing.tiempo.DIAS[inicio.weekday()]}"
        partes.append(f"Tu próximo evento: {proximo.get('titulo') or 'sin título'}, {cuando} a las {inicio:%H:%M}.")
    return " ".join(partes) if partes else "Todo tranquilo: no tienes avisos."
