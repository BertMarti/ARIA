"""ARIA: aplicacion FastAPI (login, chat con Ollama, panel de servicios, Spotify)."""
import asyncio
import json
import logging
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import auth, chat, config, services, spotify

log = logging.getLogger("aria")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Rutas accesibles sin sesion.
PUBLICAS = {"/login", "/health", "/internal/tls-ask", "/static/style.css", "/static/login.js"}


@app.on_event("startup")
async def _arranque():
    if not auth.habilitado():
        log.error("Faltan ARIA_USER / ARIA_PASSWORD o ARIA_SECRET (>=16 caracteres): login deshabilitado.")


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@app.middleware("http")
async def seguridad(request: Request, call_next):
    path = request.url.path
    # CSRF: en peticiones que modifican estado, el Origin (si existe) debe coincidir con el Host.
    if request.method not in ("GET", "HEAD", "OPTIONS") and path != "/internal/tls-ask":
        origen = request.headers.get("origin")
        if origen and urlparse(origen).netloc != request.headers.get("host"):
            return JSONResponse({"error": "Origen no permitido"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
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


@app.get("/static/app.js")
async def app_js():
    return FileResponse(config.STATIC_DIR / "app.js", media_type="text/javascript")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")


# --- API ---
def _ndjson(gen):
    async def it():
        async for ev in gen:
            yield json.dumps(ev, ensure_ascii=False) + "\n"
    return StreamingResponse(it(), media_type="application/x-ndjson",
                             headers={"X-Accel-Buffering": "no"})


@app.post("/api/chat")
async def api_chat(request: Request):
    try:
        datos = await request.json()
    except ValueError:
        return JSONResponse({"error": "JSON no válido"}, status_code=400)
    mensajes = chat.limpiar(datos.get("messages") if isinstance(datos, dict) else None)
    if not mensajes or mensajes[-1]["role"] != "user":
        return JSONResponse({"error": "Falta el mensaje del usuario"}, status_code=400)
    return _ndjson(chat.responder(mensajes))


@app.get("/api/models")
async def api_models():
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{config.OLLAMA_URL}/api/tags")
        instalados = [m["name"] for m in r.json().get("models", [])]
        ok = True
    except (httpx.HTTPError, ValueError):
        instalados, ok = [], False
    activo = config.MODEL
    presente = activo in instalados or (":" not in activo and f"{activo}:latest" in instalados)
    return {"ollama": ok, "instalados": instalados, "activo": activo, "activo_instalado": presente}


@app.post("/api/models/pull")
async def api_pull():
    """Descarga solo el modelo configurado (ARIA_MODEL), con progreso."""
    async def gen():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10)) as c:
                async with c.stream("POST", f"{config.OLLAMA_URL}/api/pull",
                                    json={"model": config.MODEL, "stream": True}) as r:
                    async for linea in r.aiter_lines():
                        if linea.strip():
                            j = json.loads(linea)
                            if j.get("error"):
                                yield {"type": "error", "text": "Error al descargar el modelo."}
                                return
                            yield {"type": "progreso", "estado": j.get("status", ""),
                                   "total": j.get("total"), "completado": j.get("completed")}
            yield {"type": "fin"}
        except httpx.HTTPError:
            yield {"type": "error", "text": "No se pudo contactar con Ollama."}
    return _ndjson(gen())


@app.get("/api/services")
async def api_services():
    return await services.estado()


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
