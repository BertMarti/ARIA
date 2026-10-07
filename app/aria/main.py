"""ARIA: aplicacion FastAPI (login, chat con Ollama, panel de servicios, Spotify)."""
import asyncio
import json
import logging
import mimetypes
import re
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .origen import origen_permitido
from . import auth, cerebros, chat, config, db, modelos, services, shield, sistema, spotify, vpn

log = logging.getLogger("aria")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Rutas accesibles sin sesion.
PUBLICAS = {"/login", "/health", "/internal/tls-ask", "/static/style.css", "/static/login.js",
            "/static/manifest.webmanifest", "/static/icon.svg"}
mimetypes.add_type("application/manifest+json", ".webmanifest")


@app.on_event("startup")
async def _arranque():
    if not auth.habilitado():
        log.error("Faltan ARIA_USER / ARIA_PASSWORD o ARIA_SECRET (>=16 caracteres): login deshabilitado.")
    db.iniciar()


@app.on_event("shutdown")
async def _parada():
    await shield.cerrar()  # Pi-hole limita las sesiones de API: se libera la nuestra


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@app.middleware("http")
async def seguridad(request: Request, call_next):
    path = request.url.path
    # CSRF: en peticiones que modifican estado, el Origin (si existe) debe coincidir con el Host.
    if request.method not in ("GET", "HEAD", "OPTIONS") and path != "/internal/tls-ask":
        if not origen_permitido(request.headers.get("origin"), request.headers.get("host"),
                                request.headers.get("sec-fetch-site"), request.headers.get("referer")):
            return JSONResponse({"error": "Origen no permitido"}, status_code=403)
    if path not in PUBLICAS and not auth.sesion_valida(request.cookies.get(auth.COOKIE)):
        if path.startswith("/api/"):
            return JSONResponse({"error": "No autenticado"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    resp = await call_next(request)
    resp.headers.setdefault("Cache-Control", "no-store")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'",
    )
    return resp


@app.get("/health")
async def health():
    return PlainTextResponse("ok")


@app.get("/internal/tls-ask")
async def tls_ask(domain: str = ""):
    """Caddy pregunta aqui antes de emitir un certificado bajo demanda."""
    if domain.lower() in config.HOSTS:
        return PlainTextResponse("ok")
    return PlainTextResponse("no", status_code=403)


# --- Login ---
@app.get("/login")
async def login_page():
    return FileResponse(config.STATIC_DIR / "login.html")


@app.post("/login")
async def login(request: Request):
    ip = _ip(request)
    if (resto := auth.bloqueado(ip)):
        return RedirectResponse(f"/login?e=bloqueado&s={resto}", status_code=303)
    cuerpo = parse_qs((await request.body())[:4096].decode("utf-8", "replace"))
    user = cuerpo.get("usuario", [""])[0]
    pwd = cuerpo.get("password", [""])[0]
    if not auth.credenciales_ok(user, pwd):
        auth.registrar_fallo(ip)
        await asyncio.sleep(1)
        return RedirectResponse("/login?e=1", status_code=303)
    auth.limpiar_fallos(ip)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(auth.COOKIE, auth.crear_sesion(), max_age=auth.MAX_AGE,
                    httponly=True, secure=True, samesite="lax", path="/")
    return resp


@app.post("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


# --- Paginas ---
@app.get("/")
async def index():
    return FileResponse(config.STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


# --- API ---
def _ndjson(gen):
    async def it():
        try:
            async for ev in gen:
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        finally:
            await gen.aclose()  # asegura que se guarda lo generado si el cliente aborta
    return StreamingResponse(it(), media_type="application/x-ndjson",
                             headers={"X-Accel-Buffering": "no"})


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


@app.get("/api/info")
async def api_info():
    primero = cerebros.cadena()[0]
    return {"version": config.VERSION, "modelo": config.modelo_activo(), "usuario": config.NOMBRE_USUARIO,
            "cerebro": {"id": primero.id, "etiqueta": primero.etiqueta()},
            "puertos": {"shield_web": config.SHIELD_WEB_PORT, "vpn": config.HEIMDALL_PORT}}


@app.get("/api/certificado")
async def api_certificado():
    """Certificado raíz PÚBLICO de la CA interna de Caddy (lo copia install.sh a data/)."""
    ruta = config.DATA_DIR / "aria-certificado.crt"
    if not ruta.is_file():
        return JSONResponse({"error": "Certificado no disponible. Ejecuta ./install.sh de nuevo."}, status_code=404)
    return FileResponse(ruta, media_type="application/x-x509-ca-cert", filename="ARIA-certificado.crt")


@app.post("/api/secret/{app_id}")
async def api_secreto(app_id: str):
    """Devuelve la contraseña de administración de un panel (solo a una sesión autenticada).
    Nunca va embebida en el HTML; la respuesta no se cachea."""
    if app_id == "shield" and config.SHIELD_PASSWORD:
        datos = {"usuario": "", "password": config.SHIELD_PASSWORD}
    elif app_id == "vpn" and config.VPN_PASSWORD:
        datos = {"usuario": config.VPN_USER, "password": config.VPN_PASSWORD}
    else:
        return JSONResponse({"error": "No hay contraseña configurada para esa aplicación."}, status_code=404)
    return JSONResponse(datos, headers={"Cache-Control": "no-store"})


# --- Conversaciones ---
@app.post("/api/chat")
async def api_chat(request: Request):
    d = await _json(request)
    texto = d.get("message")
    cid = d.get("conversation_id")
    if not isinstance(texto, str) or not texto.strip():
        return JSONResponse({"error": "Falta el mensaje"}, status_code=400)
    if cid is not None and (not isinstance(cid, str) or not db.existe(cid)):
        cid = None
    return _ndjson(chat.conversar(cid, texto))


@app.get("/api/conversations")
async def api_conversaciones():
    return {"conversaciones": await asyncio.to_thread(db.listar)}


@app.get("/api/conversations/{cid}")
async def api_conversacion(cid: str):
    c = await asyncio.to_thread(db.obtener, cid)
    if not c:
        return JSONResponse({"error": "Conversación no encontrada"}, status_code=404)
    return c


@app.patch("/api/conversations/{cid}")
async def api_renombrar(cid: str, request: Request):
    d = await _json(request)
    t = d.get("titulo")
    if not isinstance(t, str) or not t.strip() or not await asyncio.to_thread(db.renombrar, cid, t):
        return JSONResponse({"error": "No se pudo renombrar"}, status_code=400)
    return {"ok": True}


@app.delete("/api/conversations/{cid}")
async def api_borrar_conversacion(cid: str):
    if not await asyncio.to_thread(db.borrar, cid):
        return JSONResponse({"error": "Conversación no encontrada"}, status_code=404)
    return {"ok": True}


# --- Modelos ---
# --- Cerebros (cadena de proveedores de IA) ---
@app.get("/api/brains")
async def api_cerebros():
    return {"cerebros": cerebros.estado()}


@app.post("/api/brains")
async def api_cerebros_guardar(request: Request):
    d = await _json(request)
    orden, apagados = d.get("orden"), d.get("desactivados", [])
    ok = (isinstance(orden, list) and isinstance(apagados, list)
          and all(isinstance(i, str) for i in orden + apagados))
    if not ok or set(orden) != set(cerebros.PROVEEDORES) or len(set(orden)) != len(orden) \
            or not set(apagados) <= set(cerebros.PROVEEDORES):
        return JSONResponse({"error": "Orden de cerebros no válido."}, status_code=400)
    cerebros.guardar(orden, apagados)
    return {"cerebros": cerebros.estado()}


@app.post("/api/brains/test")
async def api_cerebros_probar(request: Request):
    pid = (await _json(request)).get("id")
    if pid not in cerebros.PROVEEDORES:
        return JSONResponse({"error": "Cerebro desconocido."}, status_code=400)
    return await cerebros.probar(pid)


@app.get("/api/models")
async def api_models():
    lista = await modelos.instalados()
    activo = config.modelo_activo()
    return {"ollama": lista is not None, "instalados": lista or [], "activo": activo,
            "activo_instalado": bool(lista) and modelos.esta_instalado(activo, lista),
            "curados": modelos.CURADOS}


@app.post("/api/models/activate")
async def api_activar_modelo(request: Request):
    nombre = (await _json(request)).get("model")
    lista = await modelos.instalados()
    if not isinstance(nombre, str) or lista is None or not modelos.esta_instalado(nombre, lista):
        return JSONResponse({"error": "El modelo no está instalado."}, status_code=400)
    config.guardar_modelo(nombre)
    return {"activo": nombre}


@app.post("/api/models/pull")
async def api_pull(request: Request):
    """Descarga un modelo de la lista curada (o, sin cuerpo, el modelo activo)."""
    nombre = (await _json(request)).get("model") or config.modelo_activo()
    if nombre not in modelos.NOMBRES_CURADOS and nombre != config.modelo_activo():
        return JSONResponse({"error": "Modelo no permitido."}, status_code=400)
    return _ndjson(modelos.descargar(nombre))


@app.delete("/api/models")
async def api_borrar_modelo(request: Request):
    nombre = (await _json(request)).get("model")
    lista = await modelos.instalados()
    if not isinstance(nombre, str) or lista is None or not modelos.esta_instalado(nombre, lista):
        return JSONResponse({"error": "El modelo no está instalado."}, status_code=400)
    if nombre == config.modelo_activo():
        return JSONResponse({"error": "No se puede borrar el modelo activo."}, status_code=400)
    if not await modelos.borrar(nombre):
        return JSONResponse({"error": "Ollama no pudo borrar el modelo."}, status_code=502)
    return {"ok": True}


# --- Ajustes ---
@app.post("/api/password")
async def api_password(request: Request):
    ip = _ip(request)
    if (resto := auth.bloqueado(ip)):
        return JSONResponse({"error": f"Demasiados intentos. Espera {resto} s."}, status_code=429)
    d = await _json(request)
    vals = [d.get(k) for k in ("actual", "nueva", "repetida")]
    if not all(isinstance(v, str) for v in vals):
        return JSONResponse({"error": "Faltan datos."}, status_code=400)
    err = await asyncio.to_thread(auth.cambiar_password, *vals)
    if err:
        if err.startswith("La contraseña actual"):
            auth.registrar_fallo(ip)
        return JSONResponse({"error": err}, status_code=400)
    auth.limpiar_fallos(ip)
    # La versión de sesión cambió: las demás sesiones quedan invalidadas; esta se renueva.
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, auth.crear_sesion(), max_age=auth.MAX_AGE,
                    httponly=True, secure=True, samesite="lax", path="/")
    return resp


# --- Centro de control ---
@app.get("/api/services")
async def api_services():
    return await services.estado()


def _no_conectado(msg: str) -> dict:
    return {"conectado": False, "mensaje": msg}


@app.get("/api/shield")
async def api_shield():
    if not shield.configurado():
        return _no_conectado("SHIELD-DNS no está conectado. Añade SHIELD_URL y SHIELD_PASSWORD al archivo .env y ejecuta docker compose up -d.")
    try:
        return {"conectado": True, **await shield.resumen()}
    except shield.ShieldError as e:
        return {"conectado": False, "error": True, "mensaje": str(e)}


@app.post("/api/shield/pause")
async def api_shield_pausa(request: Request):
    d = await _json(request)
    m = d.get("minutos")
    if not isinstance(m, int) or isinstance(m, bool):
        return JSONResponse({"error": "Indica los minutos (1-120)."}, status_code=400)
    try:
        return await shield.pausar(m)
    except shield.ShieldError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/shield/resume")
async def api_shield_reanudar():
    try:
        return await shield.reanudar()
    except shield.ShieldError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/system")
async def api_system():
    return await asyncio.to_thread(sistema.estado)


@app.get("/api/vpn/clients")
async def api_vpn_lista():
    if not vpn.configurado():
        return _no_conectado("HEIMDALL no está conectado. Añade VPN_USER y VPN_PASSWORD al archivo .env y ejecuta docker compose up -d.")
    try:
        return {"conectado": True, "clientes": await vpn.listar(), "panel": vpn.panel_url()}
    except vpn.VpnError as e:
        return {"conectado": False, "error": True, "mensaje": str(e)}


def _vpn_error(e: Exception) -> JSONResponse:
    return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/vpn/clients")
async def api_vpn_crear(request: Request):
    nombre = (await _json(request)).get("nombre")
    try:
        return {"id": await vpn.crear(nombre if isinstance(nombre, str) else "")}
    except vpn.VpnError as e:
        return _vpn_error(e)


@app.get("/api/vpn/clients/{cid}/qrcode.svg")
async def api_vpn_qr(cid: int):
    try:
        svg = await vpn.qr(cid)
    except vpn.VpnError as e:
        return _vpn_error(e)
    return Response(svg, media_type="image/svg+xml")


@app.get("/api/vpn/clients/{cid}/config")
async def api_vpn_conf(cid: int):
    try:
        datos = await vpn.configuracion(cid)
        nombre = next((c["nombre"] for c in await vpn.listar() if c["id"] == cid), "")
    except vpn.VpnError as e:
        return _vpn_error(e)
    seguro = re.sub(r"[^A-Za-z0-9._-]+", "_", nombre or f"cliente{cid}").strip("_") or f"cliente{cid}"
    return Response(datos, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{seguro}.conf"'})


@app.post("/api/vpn/clients/{cid}/{accion}")
async def api_vpn_accion(cid: int, accion: str):
    if accion not in ("enable", "disable"):
        return JSONResponse({"error": "Acción desconocida"}, status_code=404)
    try:
        await vpn.activar(cid, accion == "enable")
    except vpn.VpnError as e:
        return _vpn_error(e)
    return {"ok": True}


@app.delete("/api/vpn/clients/{cid}")
async def api_vpn_borrar(cid: int):
    try:
        await vpn.eliminar(cid)
    except vpn.VpnError as e:
        return _vpn_error(e)
    return {"ok": True}


@app.get("/api/spotify/status")
async def api_spotify_status():
    out = {"configurado": spotify.configured(), "conectado": spotify.connected(),
           "redirect_uri": config.SPOTIFY_REDIRECT_URI}
    if out["configurado"] and out["conectado"]:
        try:
            out["ahora"] = await spotify.current()
        except spotify.SpotifyError as e:
            out["error"] = str(e)
    return out


@app.post("/api/spotify/{accion}")
async def api_spotify_action(accion: str):
    acciones = {"play": spotify.play, "pause": spotify.pause,
                "next": spotify.next_track, "previous": spotify.previous_track}
    if accion not in acciones:
        return JSONResponse({"error": "Acción desconocida"}, status_code=404)
    try:
        return {"mensaje": await acciones[accion]()}
    except spotify.SpotifyError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/spotify/login")
async def spotify_login():
    if not spotify.configured():
        return RedirectResponse("/", status_code=303)
    estado = spotify.new_state()
    resp = RedirectResponse(spotify.auth_url(estado), status_code=303)
    resp.set_cookie("aria_spotify_state", estado, max_age=600, httponly=True,
                    secure=True, samesite="lax", path="/spotify")
    return resp


@app.get("/spotify/callback")
async def spotify_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    esperado = request.cookies.get("aria_spotify_state", "")
    if error or not code or not esperado or state != esperado:
        return RedirectResponse("/?spotify=error", status_code=303)
    try:
        await spotify.exchange_code(code)
    except (spotify.SpotifyError, httpx.HTTPError):
        return RedirectResponse("/?spotify=error", status_code=303)
    resp = RedirectResponse("/?spotify=ok", status_code=303)
    resp.delete_cookie("aria_spotify_state", path="/spotify")
    return resp
