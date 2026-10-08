"""ARIA: aplicacion FastAPI (login, chat con Ollama, panel de servicios, Spotify)."""
import asyncio
import hashlib
import html
import json
import logging
import mimetypes
import os
import re
from datetime import date
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .origen import origen_permitido
from . import agentes, api_avisos, api_control, api_finanzas, api_informacion, api_modulos, api_red, api_rutinas, arranque, auth, avisos, avisos_chequeos, briefing, cerebros, chat, config, control, cve, db, diario, finanzas, informacion, memoria, modelos, modulos, permisos, push, recordatorios, red, rutinas, services, shield, sistema, spotify, sso, telegram, tiempo, usuarios, vision, voz, vpn

log = logging.getLogger("aria")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Rutas accesibles sin sesion.
LIBRES = {"/health", "/internal/tls-ask", "/static/style.css", "/static/login.js",
          "/static/manifest.webmanifest", "/static/icon.svg", "/sw.js"}
PUBLICAS = LIBRES | {"/login"}
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; worker-src 'self'; "
       "frame-ancestors 'none'")
# El micrófono solo para ARIA (ni iframes ni otros orígenes); cámara y ubicación, para nadie.
PERMISOS_NAVEGADOR = "microphone=(self), camera=(), geolocation=()"
mimetypes.add_type("application/manifest+json", ".webmanifest")



# --- Páginas HTML con versión en los recursos (el navegador nunca usa CSS/JS de una versión anterior) ---
def _version_estaticos() -> str:
    h = hashlib.sha1()
    for f in sorted(config.STATIC_DIR.rglob("*")):
        if f.is_file():
            h.update(f.name.encode()); h.update(f.read_bytes())
    return h.hexdigest()[:10]


_VERSION_ESTATICOS = _version_estaticos()
_PAGINAS: dict = {}


def _html_versionado(nombre: str) -> HTMLResponse:
    if nombre not in _PAGINAS:
        contenido = (config.STATIC_DIR / nombre).read_text(encoding="utf-8")
        _PAGINAS[nombre] = re.sub(r'(/static/[\w.-]+\.(?:css|js|svg|webmanifest))"',
                                  lambda m: f'{m.group(1)}?v={_VERSION_ESTATICOS}"', contenido)
    return HTMLResponse(_PAGINAS[nombre], headers={"Cache-Control": "no-store"})

@app.on_event("startup")
async def _arranque():
    if not auth.habilitado():
        log.error("Faltan ARIA_USER / ARIA_PASSWORD o ARIA_SECRET (>=16 caracteres): login deshabilitado.")
    db.iniciar()
    usuarios.iniciar()
    finanzas.iniciar()
    red.iniciar()
    control.iniciar()
    cve.iniciar()
    # Diario: planificador interno (03:30 locales + recuperación de días perdidos). Sin contenedor nuevo.
    app.state.diario = asyncio.create_task(diario.bucle())
    # Avisos: tablas, chequeos, canales y planificador (recordatorios, resumen programado). Telegram con long polling.
    avisos.iniciar()
    recordatorios.iniciar()
    rutinas.iniciar()
    push.iniciar()
    telegram.iniciar()
    avisos_chequeos.registrar()
    avisos.registrar_canal("push", push.canal)
    avisos.registrar_canal("telegram", telegram.canal)
    app.state.avisos = asyncio.create_task(avisos.bucle())
    # Control parental: reconcilia SHIELD-DNS con pausas, servicios y horarios cada 30 s (idempotente).
    app.state.control = asyncio.create_task(control.bucle()) if config.CONTROL else None
    app.state.telegram = asyncio.create_task(telegram.bucle()) if telegram.configurado() else None
    # Informe de arranque: si la Raspberry se reinició, avisa al volver (y deja un latido cada minuto).
    app.state.arranque = asyncio.create_task(arranque.bucle())


@app.on_event("shutdown")
async def _parada():
    for nombre in ("diario", "avisos", "telegram", "control", "arranque"):
        tarea = getattr(app.state, nombre, None)
        if tarea:
            tarea.cancel()
    await shield.cerrar()  # Pi-hole limita las sesiones de API: se libera la nuestra


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _host(request: Request) -> str:
    return (request.headers.get("host") or "").rsplit(":", 1)[0].lower().strip("[]")


def _es_publico(request: Request) -> bool:
    """¿Se entra por el dominio público (túnel de Cloudflare) y no por la LAN?"""
    h = _host(request)
    return bool(h) and h not in config.HOSTS and not h.endswith((".local", ".lan", ".localhost")) and h != "localhost"


def _cookie(resp, usuario: dict):
    resp.set_cookie(auth.COOKIE, auth.crear_sesion(usuario), max_age=auth.MAX_AGE,
                    httponly=True, secure=True, samesite="lax", path="/")
    return resp


def _pagina(titulo: str, cuerpo: str, estado: int = 200, refresco: int = 0) -> HTMLResponse:
    meta = f'<meta http-equiv="refresh" content="{refresco}">' if refresco else ""
    doc = (f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width, initial-scale=1">{meta}'
           f'<title>ARIA - {html.escape(titulo)}</title><link rel="icon" href="/static/icon.svg" type="image/svg+xml">'
           f'<link rel="stylesheet" href="/static/style.css"></head><body class="login"><main class="login-box">'
           f'<img class="login-logo" src="/static/icon.svg" alt="" width="72" height="72"><h1>ARIA</h1>{cuerpo}'
           f'</main></body></html>')
    return HTMLResponse(doc, status_code=estado, headers={"Cache-Control": "no-store", "Content-Security-Policy": CSP,
                                                          "Permissions-Policy": PERMISOS_NAVEGADOR,
                                                          **({"Retry-After": str(refresco)} if refresco else {})})


def _sin_acceso(email: str) -> HTMLResponse:
    # El email viene de un JWT verificado, pero se escapa igualmente.
    return _pagina("Sin acceso", f'<p class="error">Tu cuenta ({html.escape(email)}) no tiene acceso a ARIA. '
                   f'Pide al administrador que te invite.</p>'
                   f'<p class="sub"><a href="{html.escape(sso.url_salida())}">Salir de Cloudflare</a></p>', 403)


def _entrando() -> HTMLResponse:
    return _pagina("Entrando", '<p class="sub">Entrando con tu cuenta de Cloudflare…</p>', 503, refresco=3)


@app.middleware("http")
async def seguridad(request: Request, call_next):
    path = request.url.path
    # CSRF: en peticiones que modifican estado, el Origin (si existe) debe coincidir con el Host.
    if request.method not in ("GET", "HEAD", "OPTIONS") and path != "/internal/tls-ask":
        if not origen_permitido(request.headers.get("origin"), request.headers.get("host"),
                                request.headers.get("sec-fetch-site"), request.headers.get("referer")):
            return JSONResponse({"error": "Origen no permitido"}, status_code=403)
    es_api = path.startswith("/api/")
    nueva = None          # usuario para el que hay que emitir cookie de sesión
    pendiente = False     # SSO: Cloudflare no respondió, hay que reintentar
    usuario = None
    if path not in LIBRES:
        usuario = auth.sesion_usuario(request.cookies.get(auth.COOKIE))
        token = request.headers.get(sso.CABECERA)
        if token and sso.habilitado():
            estado, email = await sso.identificar(token)
            if estado == sso.OK and (usuario is None or usuario["email"] != email):
                u = await asyncio.to_thread(usuarios.por_sso, email)
                if u is None or not u["activo"]:
                    if es_api:
                        return JSONResponse({"error": "Tu cuenta no tiene acceso a ARIA."}, status_code=403)
                    return _sin_acceso(email)
                usuario, nueva = u, u
                await asyncio.to_thread(usuarios.tocar_acceso, u["id"])
            elif estado == sso.TRANSITORIO and usuario is None:
                pendiente = True
        request.state.usuario = usuario
        if path == "/login" and request.method == "GET" and (usuario or pendiente):
            if pendiente:
                return _entrando()
            return _cookie(RedirectResponse("/", status_code=303), nueva) if nueva else RedirectResponse("/", status_code=303)
        if path != "/login":
            if usuario is None:
                if pendiente and not es_api:
                    return _entrando()
                if es_api:
                    return JSONResponse({"error": "No autenticado"}, status_code=401)
                return RedirectResponse("/login", status_code=303)
            if not permisos.permitido(usuario["rol"], request.method, path):
                return JSONResponse({"error": "No tienes permiso para esto."}, status_code=403)
    resp = await call_next(request)
    if nueva:
        _cookie(resp, nueva)
    resp.headers.setdefault("Cache-Control", "no-store")
    resp.headers.setdefault("Content-Security-Policy", CSP)
    resp.headers.setdefault("Permissions-Policy", PERMISOS_NAVEGADOR)
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
    return _html_versionado("login.html")


@app.post("/login")
async def login(request: Request):
    ip = _ip(request)
    if (resto := auth.bloqueado(ip)):
        return RedirectResponse(f"/login?e=bloqueado&s={resto}", status_code=303)
    cuerpo = parse_qs((await request.body())[:4096].decode("utf-8", "replace"))
    ident = cuerpo.get("usuario", [""])[0]
    pwd = cuerpo.get("password", [""])[0]
    u = await asyncio.to_thread(usuarios.autenticar, ident, pwd) if auth.habilitado() else None
    if not u:
        auth.registrar_fallo(ip)
        await asyncio.sleep(1)
        return RedirectResponse("/login?e=1", status_code=303)
    auth.limpiar_fallos(ip)
    await asyncio.to_thread(usuarios.tocar_acceso, u["id"])
    return _cookie(RedirectResponse("/", status_code=303), u)


@app.post("/logout")
async def logout(request: Request):
    # Por el dominio público hay que cerrar también la sesión de Cloudflare Access.
    destino = sso.url_salida() if sso.habilitado() and _es_publico(request) else "/login"
    resp = RedirectResponse(destino, status_code=303)
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


# --- Paginas ---
@app.get("/")
async def index():
    return _html_versionado("index.html")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
app.include_router(api_finanzas.router)
app.include_router(api_red.router)
app.include_router(api_control.router)
app.include_router(api_avisos.router)
app.include_router(api_rutinas.router)
app.include_router(api_modulos.router)
app.include_router(api_informacion.router)
# Módulos de modulos/ (o ARIA_MODULOS_DIR): se cargan al importar para que sus rutas existan antes de servir.
# Un módulo roto nunca impide arrancar (queda en «error» en Ajustes → Módulos).
modulos.cargar(app)


@app.get("/sw.js")
async def service_worker():
    """Service worker de las notificaciones push. Se sirve desde la raíz (alcance «/») y lleva la versión
    de los estáticos para que el navegador lo actualice. No guarda nada en caché."""
    if "sw" not in _PAGINAS:
        _PAGINAS["sw"] = (config.STATIC_DIR / "sw.js").read_text(encoding="utf-8").replace("__VERSION__", _VERSION_ESTATICOS)
    return Response(_PAGINAS["sw"], media_type="text/javascript",
                    headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


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
async def api_info(request: Request):
    u = request.state.usuario
    primero = cerebros.cadena()[0]
    return {"version": config.VERSION, "modelo": config.modelo_activo(), "usuario": u["nombre"],
            "email": u["email"], "rol": u["rol"], "tiene_password": u["tiene_password"],
            "cerebro": {"id": primero.id, "etiqueta": primero.etiqueta()},
            "puertos": {"shield_web": config.SHIELD_WEB_PORT, "vpn": config.HEIMDALL_PORT},
            "funciones": {"spotify": config.SPOTIFY, "netflix": config.NETFLIX, "vision": vision.disponible()}}


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
# Cuerpo máximo de /api/chat: una imagen de 5 MB en base64 (~6,7 MB) más el texto.
MAX_CUERPO_CHAT = 7_200_000


async def _json_limitado(request: Request, maximo: int) -> dict | None:
    """Como `_json`, pero sin leer más de `maximo` bytes (None = demasiado grande)."""
    largo = request.headers.get("content-length", "")
    if largo.isdigit() and int(largo) > maximo:
        return None
    cuerpo = bytearray()
    async for parte in request.stream():
        cuerpo += parte
        if len(cuerpo) > maximo:
            return None
    try:
        d = json.loads(bytes(cuerpo))
    except ValueError:
        return {}
    finally:
        cuerpo.clear()
    return d if isinstance(d, dict) else {}


@app.post("/api/chat")
async def api_chat(request: Request):
    """Mensaje del chat (NDJSON). Con `imagen` (data URL JPEG/PNG/WebP, ≤ 5 MB) responde un cerebro con visión;
    la imagen solo vive en memoria durante la petición."""
    u = request.state.usuario
    d = await _json_limitado(request, MAX_CUERPO_CHAT)
    if d is None:
        return JSONResponse({"error": "La imagen es demasiado grande (máximo 5 MB)."}, status_code=413)
    texto = d.get("message")
    cid = d.get("conversation_id")
    imagen = d.pop("imagen", None)
    if imagen is not None:
        if texto is not None and not isinstance(texto, str):
            return JSONResponse({"error": "Mensaje no válido"}, status_code=400)
        if cid is not None and (not isinstance(cid, str) or not db.existe(cid, u["id"])):
            cid = None
        try:
            datos, mime = vision.desde_data_url(imagen)
        except vision.VisionError as e:
            return JSONResponse({"error": e.mensaje}, status_code=e.estado)
        finally:
            imagen = None
        if not vision.disponible():
            return JSONResponse({"error": vision.NO_DISPONIBLE}, status_code=503)
        if (resto := vision.limitar(u["id"])):
            return JSONResponse({"error": f"Demasiadas imágenes seguidas. Espera {resto} s."},
                                status_code=429, headers={"Retry-After": str(resto)})
        return _ndjson(chat.conversar_imagen(u, cid, texto or "", datos, mime))
    if not isinstance(texto, str) or not texto.strip():
        return JSONResponse({"error": "Falta el mensaje"}, status_code=400)
    if cid is not None and (not isinstance(cid, str) or not db.existe(cid, u["id"])):
        cid = None
    agente = d.get("agente")
    if agente is not None and (not isinstance(agente, str) or agente not in agentes.AGENTES):
        return JSONResponse({"error": "Agente desconocido"}, status_code=400)
    if agente and not agentes.permitido(agente, u["rol"]):
        return JSONResponse({"error": "Ese agente es solo para administradores."}, status_code=403)
    return _ndjson(chat.conversar(u, cid, texto, agente))


# --- Tickets leídos de una imagen: el usuario confirma (o descarta) apuntarlos en sus finanzas ---
TOKEN_TICKET = r"[A-Za-z0-9_-]{16,64}"


@app.post("/api/vision/tickets/{token}")
async def api_ticket_registrar(token: str, request: Request):
    u = request.state.usuario
    p = vision.tomar(u["id"], token) if re.fullmatch(TOKEN_TICKET, token) else None
    if not p:
        return JSONResponse({"error": "Esta propuesta ya no existe o ha caducado."}, status_code=404)
    ok, texto = await vision.registrar_ticket(u, p["ticket"], p["cid"])
    if not ok:
        return JSONResponse({"error": texto}, status_code=400)
    return {"ok": True, "texto": texto}


@app.delete("/api/vision/tickets/{token}")
async def api_ticket_descartar(token: str, request: Request):
    p = vision.tomar(request.state.usuario["id"], token) if re.fullmatch(TOKEN_TICKET, token) else None
    if not p:
        return JSONResponse({"error": "Esta propuesta ya no existe o ha caducado."}, status_code=404)
    return {"ok": True}


@app.get("/api/agentes")
async def api_agentes(request: Request):
    return {"agentes": agentes.disponibles(request.state.usuario["rol"]), "defecto": agentes.AUTO}


@app.get("/api/conversations")
async def api_conversaciones(request: Request):
    return {"conversaciones": await asyncio.to_thread(db.listar, request.state.usuario["id"])}


@app.get("/api/conversations/{cid}")
async def api_conversacion(cid: str, request: Request):
    c = await asyncio.to_thread(db.obtener, cid, request.state.usuario["id"])
    if not c:
        return JSONResponse({"error": "Conversación no encontrada"}, status_code=404)
    return c


@app.patch("/api/conversations/{cid}")
async def api_renombrar(cid: str, request: Request):
    d = await _json(request)
    u = request.state.usuario
    if "agente" in d:  # selector de agente de la conversación
        a = d.get("agente")
        if not isinstance(a, str) or a not in agentes.AGENTES:
            return JSONResponse({"error": "Agente desconocido"}, status_code=400)
        if not agentes.permitido(a, u["rol"]):
            return JSONResponse({"error": "Ese agente es solo para administradores."}, status_code=403)
        if not await asyncio.to_thread(db.fijar_agente, cid, u["id"], a):
            return JSONResponse({"error": "Conversación no encontrada"}, status_code=404)
        return {"ok": True}
    t = d.get("titulo")
    if not isinstance(t, str) or not t.strip() or not await asyncio.to_thread(db.renombrar, cid, request.state.usuario["id"], t):
        return JSONResponse({"error": "No se pudo renombrar"}, status_code=400)
    return {"ok": True}


@app.delete("/api/conversations/{cid}")
async def api_borrar_conversacion(cid: str, request: Request):
    if not await asyncio.to_thread(db.borrar, cid, request.state.usuario["id"]):
        return JSONResponse({"error": "Conversación no encontrada"}, status_code=404)
    return {"ok": True}


# --- Voz ---
@app.get("/api/voz/estado")
async def api_voz_estado():
    return {"groq": bool(os.environ.get("GROQ_API_KEY")), "local": await voz.voz_local_ok()}


@app.post("/api/voz/transcribir")
async def api_voz_transcribir(request: Request):
    """Audio crudo en el cuerpo (Content-Type audio/webm, ogg, wav, mp4 o mpeg). No se guarda."""
    u = request.state.usuario
    largo = request.headers.get("content-length", "")
    if largo.isdigit() and int(largo) > voz.MAX_BYTES:
        return JSONResponse({"error": "La grabación es demasiado larga."}, status_code=413)
    datos = bytearray()
    async for parte in request.stream():
        datos += parte
        if len(datos) > voz.MAX_BYTES:
            return JSONResponse({"error": "La grabación es demasiado larga."}, status_code=413)
    mime = request.headers.get("content-type")
    try:
        ext = voz.validar_audio(mime, bytes(datos))
        if (resto := voz.limitar_stt(u["id"])):
            return JSONResponse({"error": f"Demasiadas transcripciones seguidas. Espera {resto} s."},
                                status_code=429, headers={"Retry-After": str(resto)})
        return await voz.transcribir(bytes(datos), ext, voz.tipo_base(mime))
    except voz.AudioError as e:
        return JSONResponse({"error": e.mensaje}, status_code=e.estado)
    finally:
        datos.clear()  # el audio no se conserva


@app.post("/api/voz/hablar")
async def api_voz_hablar(request: Request):
    d = await _json(request)
    texto = d.get("texto")
    limpio = voz.limpiar_para_voz(texto, voz.MAX_TTS) if isinstance(texto, str) else ""
    if not limpio:
        return JSONResponse({"error": "No hay texto que leer."}, status_code=400)
    if (resto := voz.limite_tts.esperar(request.state.usuario["id"])):
        return JSONResponse({"error": f"Demasiadas peticiones de voz. Espera {resto} s."},
                            status_code=429, headers={"Retry-After": str(resto)})
    try:
        wav = await voz.sintetizar(limpio, voz.velocidad(d.get("velocidad", 1.0)))
    except voz.AudioError as e:
        return JSONResponse({"error": e.mensaje}, status_code=e.estado)
    return Response(wav, media_type="audio/wav")


@app.websocket("/api/voz/despertar")
async def ws_despertar(ws: WebSocket):
    """Escucha «manos libres»: el navegador envía PCM 16 kHz mono y aria-voz espera la palabra «Aria».

    El middleware HTTP no se aplica a los WebSocket: aquí se comprueban Origin, sesión y rol."""
    u = auth.sesion_usuario(ws.cookies.get(auth.COOKIE))
    if (not voz.origen_ws_permitido(ws.headers.get("origin"), ws.headers.get("host")) or u is None
            or not permisos.permitido(u["rol"], "GET", ws.url.path)):
        await ws.close(code=1008)  # antes de aceptar: el navegador recibe un 403
        return
    if voz._escuchas.get(u["id"], 0) >= 1:
        await ws.close(code=1013)
        return
    await ws.accept()
    voz._escuchas[u["id"]] = voz._escuchas.get(u["id"], 0) + 1
    try:
        await voz.retransmitir(ws, u["id"])
    finally:
        voz._escuchas[u["id"]] -= 1
        if not voz._escuchas[u["id"]]:
            voz._escuchas.pop(u["id"], None)


# --- Memoria (cada usuario, solo la suya; la identidad sale de la sesión, nunca de la petición) ---
FECHA_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _memoria_json(uid: int) -> dict:
    return {"recuerdos": memoria.listar(uid), "aprender": memoria.aprende(uid), "max": memoria.MAX_RECUERDOS,
            "max_texto": memoria.MAX_TEXTO, "diario": memoria.ultimos_dias(uid, 14)}


@app.get("/api/memoria")
async def api_memoria(request: Request):
    return await asyncio.to_thread(_memoria_json, request.state.usuario["id"])


@app.post("/api/memoria")
async def api_memoria_anadir(request: Request):
    d = await _json(request)
    if not isinstance(d.get("texto"), str):
        return JSONResponse({"error": "Escribe qué quieres que recuerde."}, status_code=400)
    try:
        rec, nuevo = await asyncio.to_thread(memoria.anadir, request.state.usuario["id"], d["texto"], "usuario")
    except memoria.MemoriaError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"recuerdo": rec, "creado": nuevo}


@app.post("/api/memoria/ajustes")
async def api_memoria_ajustes(request: Request):
    v = (await _json(request)).get("aprender")
    if not isinstance(v, bool):
        return JSONResponse({"error": "Valor no válido."}, status_code=400)
    await asyncio.to_thread(memoria.fijar_aprender, request.state.usuario["id"], v)
    return {"aprender": v}


@app.patch("/api/memoria/{rid}")
async def api_memoria_editar(rid: int, request: Request):
    d = await _json(request)
    if not isinstance(d.get("texto"), str):
        return JSONResponse({"error": "Escribe el texto del recuerdo."}, status_code=400)
    try:
        return {"recuerdo": await asyncio.to_thread(memoria.editar, request.state.usuario["id"], rid, d["texto"])}
    except memoria.MemoriaError as e:
        return JSONResponse({"error": str(e)}, status_code=404 if "no encontrado" in str(e) else 400)


@app.delete("/api/memoria/{rid}")
async def api_memoria_borrar(rid: int, request: Request):
    if not await asyncio.to_thread(memoria.borrar, request.state.usuario["id"], rid):
        return JSONResponse({"error": "Recuerdo no encontrado."}, status_code=404)
    return {"ok": True}


@app.delete("/api/memoria")
async def api_memoria_borrar_todo(request: Request):
    """«Borrar toda mi memoria»: recuerdos, diario y resumen de hoy del usuario que llama."""
    return {"ok": True, "borrados": await asyncio.to_thread(memoria.borrar_todo, request.state.usuario["id"])}


@app.delete("/api/diario/{fecha}")
async def api_diario_borrar(fecha: str, request: Request):
    if not FECHA_RE.fullmatch(fecha) or not await asyncio.to_thread(memoria.borrar_dia, request.state.usuario["id"], fecha):
        return JSONResponse({"error": "No hay resumen de ese día."}, status_code=404)
    return {"ok": True}


@app.post("/api/diario/generar")
async def api_diario_generar(request: Request):
    """Solo administrador (lo impone permisos.py): lanza el trabajo del diario a mano.
    Cuerpo opcional: {"fecha": "AAAA-MM-DD" (por defecto hoy), "todos": true (por defecto solo el que llama)}."""
    d = await _json(request)
    try:
        dia = date.fromisoformat(d["fecha"]) if d.get("fecha") else tiempo.hoy()
    except (ValueError, TypeError):
        return JSONResponse({"error": "Fecha no válida (AAAA-MM-DD)."}, status_code=400)
    u = request.state.usuario
    if d.get("todos") is True:
        ids = await asyncio.to_thread(diario.usuarios_con_mensajes, dia)
        nombres = await asyncio.to_thread(diario._usuarios)
        objetivos = [(i, nombres[i]) for i in ids if i in nombres]
    else:
        objetivos = [(u["id"], u["nombre"])]
    res = {str(i): await diario.generar(i, n, dia, forzar=True) for i, n in objetivos}
    return {"fecha": dia.isoformat(), "resultados": res}


@app.get("/api/briefing")
async def api_briefing(request: Request, refrescar: int = 0):
    """Resumen de buenos días del usuario (caché del día; ?refrescar=1 lo regenera). El rol `usuario` no recibe
    datos de administrador (VPN, copias)."""
    return await briefing.obtener(request.state.usuario, refrescar=bool(refrescar))


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
    u = request.state.usuario
    d = await _json(request)
    vals = [d.get(k) for k in ("actual", "nueva", "repetida")]
    if not all(isinstance(v, str) for v in vals):
        return JSONResponse({"error": "Faltan datos."}, status_code=400)
    err = await asyncio.to_thread(usuarios.cambiar_password, u["id"], *vals)
    if err:
        if err.startswith("La contraseña actual"):
            auth.registrar_fallo(ip)
        return JSONResponse({"error": err}, status_code=400)
    auth.limpiar_fallos(ip)
    # La versión de sesión cambió: las demás sesiones quedan invalidadas; esta se renueva.
    return _cookie(JSONResponse({"ok": True}), await asyncio.to_thread(usuarios.por_id, u["id"]))


# --- Usuarios (solo admin; lo impone permisos.py) ---
def _err_usuario(e: Exception) -> JSONResponse:
    return JSONResponse({"error": str(e)}, status_code=400)


@app.get("/api/users")
async def api_usuarios():
    return {"usuarios": await asyncio.to_thread(usuarios.listar)}


@app.post("/api/users")
async def api_usuarios_crear(request: Request):
    d = await _json(request)
    try:
        u = await asyncio.to_thread(usuarios.crear, d.get("email"), d.get("nombre"), d.get("rol", "usuario"),
                                    d.get("password") or None)
    except usuarios.UsuarioError as e:
        return _err_usuario(e)
    return {"usuario": u}


@app.patch("/api/users/{uid}")
async def api_usuarios_cambiar(uid: int, request: Request):
    d = await _json(request)
    activo = d.get("activo")
    if activo is not None and not isinstance(activo, bool):
        return JSONResponse({"error": "Valor de «activo» no válido."}, status_code=400)
    try:
        u = await asyncio.to_thread(usuarios.actualizar, uid, d.get("rol"), activo, d.get("nombre"))
    except usuarios.UsuarioError as e:
        return _err_usuario(e)
    return {"usuario": u}


@app.post("/api/users/{uid}/password")
async def api_usuarios_password(uid: int, request: Request):
    d = await _json(request)
    try:
        if d.get("quitar") is True:
            await asyncio.to_thread(usuarios.quitar_password, uid)
        else:
            await asyncio.to_thread(usuarios.fijar_password, uid, d.get("password"))
    except usuarios.UsuarioError as e:
        return _err_usuario(e)
    return {"ok": True}


@app.delete("/api/users/{uid}")
async def api_usuarios_borrar(uid: int):
    try:
        await asyncio.to_thread(usuarios.borrar, uid)
    except usuarios.UsuarioError as e:
        return _err_usuario(e)
    return {"ok": True}


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
async def api_vpn_lista(request: Request):
    if not vpn.configurado():
        return _no_conectado("HEIMDALL no está conectado. Añade VPN_USER y VPN_PASSWORD al archivo .env y ejecuta docker compose up -d.")
    try:
        clientes = await vpn.listar()
        if request.state.usuario["rol"] != "admin":  # los usuarios solo ven el estado, sin IP ni tráfico
            clientes = [{k: c[k] for k in ("id", "nombre", "activo", "conectado")} for c in clientes]
        return {"conectado": True, "clientes": clientes, "panel": vpn.panel_url()}
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
