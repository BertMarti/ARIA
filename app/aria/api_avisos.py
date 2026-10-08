"""API de avisos, recordatorios, Telegram y notificaciones push. Todo es del usuario de la sesión
(nunca de un id que venga en la petición); permisos.py lo abre a los dos roles."""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import avisos, config, push, recordatorios, telegram

router = APIRouter()

_lim_codigo = avisos.Limitador(5, 600)
_lim_prueba = avisos.Limitador(3, 60)
_lim_push_prueba = avisos.Limitador(5, 60)
_lim_suscribir = avisos.Limitador(10, 3600)
_lim_recordatorio = avisos.Limitador(30, 3600)


def _u(request: Request) -> dict:
    return request.state.usuario


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _demasiadas() -> JSONResponse:
    return JSONResponse({"error": "Demasiadas peticiones seguidas; espera un poco."}, status_code=429)


# --- Campana ----------------------------------------------------------------------------------------
@router.get("/api/avisos")
async def api_avisos(request: Request):
    return await asyncio.to_thread(avisos.listar, _u(request)["id"])


@router.post("/api/avisos/leidos")
async def api_avisos_todos(request: Request):
    return {"marcados": await asyncio.to_thread(avisos.marcar_todos, _u(request)["id"])}


@router.post("/api/avisos/{aid}/leido")
async def api_aviso_leido(aid: int, request: Request):
    if not await asyncio.to_thread(avisos.marcar_leido, _u(request)["id"], aid):
        return JSONResponse({"error": "Aviso no encontrado."}, status_code=404)
    return {"ok": True}


# --- Ajustes → Avisos -----------------------------------------------------------------------------------
async def _estado_ajustes(u: dict) -> dict:
    uid = u["id"]
    tg = {"configurado": telegram.configurado(), "bot": await telegram.usuario_bot() if telegram.configurado() else None,
          "chats": await asyncio.to_thread(telegram.chats_de, uid)}
    return {"ajustes": await asyncio.to_thread(avisos.ajustes, uid), "tipos": avisos.tipos_para(u["rol"]),
            "telegram": tg,
            "push": {"clave": push.claves()[0], "dispositivos": await asyncio.to_thread(push.listar, uid),
                     "url_publica": config.URL_PUBLICA}}


@router.get("/api/avisos/ajustes")
async def api_ajustes(request: Request):
    return await _estado_ajustes(_u(request))


@router.post("/api/avisos/ajustes")
async def api_ajustes_guardar(request: Request):
    d = await _json(request)
    return {"ajustes": await asyncio.to_thread(avisos.guardar_ajustes, _u(request)["id"], d)}


@router.post("/api/avisos/probar")
async def api_probar(request: Request):
    u = _u(request)
    if not _lim_prueba.permitir(u["id"]):
        return _demasiadas()
    r = await avisos.emitir("prueba", "info", "Aviso de prueba de ARIA: si lo ves, este canal funciona.", "ajustes",
                            [u["id"]], ignorar_silencio=True)
    return {"canales": r[0]["canales"] if r else []}


# --- Recordatorios -------------------------------------------------------------------------------------------
@router.get("/api/recordatorios")
async def api_recordatorios(request: Request):
    return {"recordatorios": await asyncio.to_thread(recordatorios.listar, _u(request)["id"])}


@router.post("/api/recordatorios")
async def api_recordatorio_crear(request: Request):
    u = _u(request)
    if not _lim_recordatorio.permitir(u["id"]):
        return _demasiadas()
    d = await _json(request)
    if not all(isinstance(d.get(k, ""), str) for k in ("texto", "cuando", "repetir")):
        return JSONResponse({"error": "Datos no válidos."}, status_code=400)
    try:
        r = await asyncio.to_thread(recordatorios.crear, u["id"], d.get("texto"), d.get("cuando"), d.get("repetir") or None)
    except recordatorios.RecordatorioError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"recordatorio": r}


@router.delete("/api/recordatorios/{rid}")
async def api_recordatorio_borrar(rid: int, request: Request):
    if not await asyncio.to_thread(recordatorios.borrar, _u(request)["id"], rid):
        return JSONResponse({"error": "Recordatorio no encontrado."}, status_code=404)
    return {"ok": True}


# --- Telegram -------------------------------------------------------------------------------------------------
@router.post("/api/telegram/vincular")
async def api_tg_vincular(request: Request):
    u = _u(request)
    if not telegram.configurado():
        return JSONResponse({"error": "El bot de Telegram no está configurado (TELEGRAM_BOT_TOKEN)."}, status_code=400)
    if not _lim_codigo.permitir(u["id"]):
        return _demasiadas()
    nombre = await telegram.usuario_bot()
    if not nombre:
        return JSONResponse({"error": "No se puede hablar con Telegram ahora mismo (¿token válido?)."}, status_code=502)
    c = await asyncio.to_thread(telegram.crear_codigo, u["id"])
    return {**c, "bot": nombre, "enlace": f"https://t.me/{nombre}?start={c['codigo']}"}


@router.delete("/api/telegram/chats/{chat_id}")
async def api_tg_desvincular(chat_id: int, request: Request):
    if not await asyncio.to_thread(telegram.desvincular, _u(request)["id"], chat_id):
        return JSONResponse({"error": "Chat no encontrado."}, status_code=404)
    return {"ok": True}


# --- Push -------------------------------------------------------------------------------------------------------
@router.post("/api/push/suscripciones")
async def api_push_suscribir(request: Request):
    u = _u(request)
    if not _lim_suscribir.permitir(u["id"]):
        return _demasiadas()
    d = await _json(request)
    try:
        s = await asyncio.to_thread(push.suscribir, u["id"], d.get("suscripcion"), d.get("nombre"))
    except push.PushError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"dispositivo": s}


@router.delete("/api/push/suscripciones/{sid}")
async def api_push_borrar(sid: int, request: Request):
    if not await asyncio.to_thread(push.borrar, _u(request)["id"], sid):
        return JSONResponse({"error": "Dispositivo no encontrado."}, status_code=404)
    return {"ok": True}


@router.post("/api/push/prueba")
async def api_push_prueba(request: Request):
    u = _u(request)
    if not _lim_push_prueba.permitir(u["id"]):
        return _demasiadas()
    r = await push.enviar(u["id"], "ARIA", "Notificación de prueba: este dispositivo recibe los avisos.", "/#ajustes",
                          "aria-prueba")
    return r
