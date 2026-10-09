"""Bot de Telegram de ARIA (bidireccional), con long polling (getUpdates): no hay webhook ni nada expuesto.

- Token en .env (TELEGRAM_BOT_TOKEN). Vacío = bot apagado; la interfaz explica cómo crearlo.
- Vincular: en Ajustes → Avisos se pide un código de 6 cifras (caduca en 10 min, un solo uso) y se abre
  https://t.me/<bot>?start=<código>. Ese chat queda unido a ese usuario de ARIA (se admiten varios chats).
- Solo se atienden chats privados vinculados. A los demás se les contesta, como mucho una vez cada
  10 minutos, «No te conozco…». Nada de lo escrito se ejecuta como orden salvo los comandos fijos.
- El texto pasa por el mismo chat que la web (agentes, memoria, herramientas y permisos del usuario
  vinculado); cada chat tiene su conversación en el historial de ARIA (/nuevo empieza otra).
- Los botones (callback_data) son fichas aleatorias guardadas en el servidor, ligadas al chat y al usuario,
  de un solo uso y con caducidad. Las acciones de administración piden «Confirmar» y se vuelve a comprobar
  el rol del usuario al ejecutarlas.

    docker compose exec app python -m aria.telegram --probar     # comprueba el token (getMe)
"""
import asyncio
import html
import io
import json
import logging
import re
import secrets
import sys
import time
from contextlib import closing

import httpx

from . import avisos, config, db, enlaces, recordatorios, resumen_diario, rutinas, telemetria

log = logging.getLogger("aria.telegram")

API = "https://api.telegram.org"
LIMITE = 4096
TROZO = 3800
CODIGO_S = 600
MAX_VOZ_S = 120
MAX_VOZ_BYTES = 1_000_000
MAX_TEXTO = 4000

COMANDOS = [
    ("estado", "Resumen de la casa"), ("resumen", "Resumen de buenos días"), ("tiempo", "Previsión del tiempo"),
    ("recordatorios", "Tus recordatorios"), ("rutinas", "Tus rutinas programadas"), ("gastos", "Gastos de este mes"),
    ("red", "Salud de la red y dispositivos nuevos"), ("vpn", "Dispositivos de la VPN"),
    ("bloqueo", "Bloqueador de anuncios (SHIELD)"), ("informe", "Informe semanal (admin)"),
    ("nuevovpn", "Nuevo dispositivo VPN (admin)"),
    ("reiniciar", "Reiniciar la Raspberry (admin)"),
    ("control", "Control parental: dispositivos pausados o bloqueados (admin)"),
    ("nuevo", "Empezar otra conversación"), ("desvincular", "Desvincular este chat"), ("ayuda", "Ayuda"),
]
OPS_ADMIN = {"pausar", "reanudar", "nuevovpn", "reiniciar"}

NO_TE_CONOZCO = "No te conozco. Vincula este chat desde ARIA → Ajustes → Avisos."


class TelegramError(Exception):
    def __init__(self, codigo: int, descripcion: str):
        super().__init__(f"{codigo}: {descripcion}")
        self.codigo, self.descripcion = codigo, descripcion


class BotAPI:
    """Cliente mínimo de la Bot API. El token va en la URL: nunca se registra ninguna URL ni excepción completa."""

    def __init__(self, token: str):
        self._token = token

    async def llamar(self, metodo: str, espera: float = 20, **datos):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(espera, connect=10)) as c:
                r = await c.post(f"{API}/bot{self._token}/{metodo}", json=datos)
            j = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise TelegramError(0, f"sin conexión ({type(e).__name__})") from None
        if not j.get("ok"):
            raise TelegramError(int(j.get("error_code") or r.status_code), str(j.get("description", ""))[:200])
        return j.get("result")

    async def subir(self, metodo: str, campo: str, nombre: str, contenido: bytes, mime: str, **datos):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as c:
                r = await c.post(f"{API}/bot{self._token}/{metodo}", files={campo: (nombre, contenido, mime)},
                                 data={k: (json.dumps(v) if isinstance(v, (dict, list)) else str(v)) for k, v in datos.items()})
            j = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise TelegramError(0, f"sin conexión ({type(e).__name__})") from None
        if not j.get("ok"):
            raise TelegramError(int(j.get("error_code") or r.status_code), str(j.get("description", ""))[:200])
        return j.get("result")

    async def descargar(self, ruta: str, maximo: int = MAX_VOZ_BYTES) -> bytes:
        if not re.fullmatch(r"[\w./-]{1,200}", ruta or "") or ".." in ruta:
            raise TelegramError(400, "ruta de archivo no válida")
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(f"{API}/file/bot{self._token}/{ruta}")
        except httpx.HTTPError as e:
            raise TelegramError(0, f"sin conexión ({type(e).__name__})") from None
        if r.status_code != 200 or len(r.content) > maximo:
            raise TelegramError(r.status_code, "no se pudo descargar")
        return r.content


_bot: BotAPI | None = None
_yo: dict = {}


def configurado() -> bool:
    return bool(config.TELEGRAM_TOKEN)


def bot() -> BotAPI | None:
    global _bot
    if _bot is None and configurado():
        _bot = BotAPI(config.TELEGRAM_TOKEN)
    return _bot


def fijar_bot(b) -> None:
    """Para las pruebas (Bot API falsa)."""
    global _bot
    _bot = b


async def usuario_bot() -> str | None:
    """@usuario del bot (getMe, en caché)."""
    if _yo.get("username"):
        return _yo["username"]
    b = bot()
    if not b:
        return None
    try:
        _yo.update(await b.llamar("getMe"))
    except TelegramError:
        return None
    return _yo.get("username")


# --- Base de datos --------------------------------------------------------------------------------------
def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS telegram_chats (
                chat_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL DEFAULT '', conv_id TEXT, vinculado REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS telegram_codigos (
                codigo TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                expira REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS telegram_acciones (
                token TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                accion TEXT NOT NULL, datos TEXT NOT NULL, expira REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS telegram_estado (clave TEXT PRIMARY KEY, valor TEXT NOT NULL);
        """)


def crear_codigo(uid: int, ahora: float | None = None) -> dict:
    ahora = time.time() if ahora is None else ahora
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM telegram_codigos WHERE expira<? OR user_id=?", (ahora, uid))
        while True:
            codigo = f"{secrets.randbelow(10 ** 6):06d}"
            if not con.execute("SELECT 1 FROM telegram_codigos WHERE codigo=?", (codigo,)).fetchone():
                break
        con.execute("INSERT INTO telegram_codigos (codigo, user_id, expira) VALUES (?,?,?)", (codigo, uid, ahora + CODIGO_S))
    return {"codigo": codigo, "expira": ahora + CODIGO_S}


def canjear_codigo(codigo: str, chat_id: int, nombre: str, ahora: float | None = None) -> int | None:
    """Vincula el chat al usuario del código (un solo uso). Devuelve el user_id o None."""
    ahora = time.time() if ahora is None else ahora
    if not re.fullmatch(r"\d{6}", codigo or ""):
        return None
    with closing(db._con()) as con, con:
        r = con.execute("SELECT user_id FROM telegram_codigos WHERE codigo=? AND expira>=?", (codigo, ahora)).fetchone()
        if not r:
            return None
        con.execute("DELETE FROM telegram_codigos WHERE codigo=?", (codigo,))
        con.execute("INSERT INTO telegram_chats (chat_id, user_id, nombre, vinculado) VALUES (?,?,?,?) "
                    "ON CONFLICT(chat_id) DO UPDATE SET user_id=excluded.user_id, nombre=excluded.nombre, "
                    "conv_id=NULL, vinculado=excluded.vinculado", (chat_id, r["user_id"], nombre[:60], ahora))
        return r["user_id"]


def chat_vinculado(chat_id: int) -> dict | None:
    with closing(db._con()) as con:
        r = con.execute("SELECT * FROM telegram_chats WHERE chat_id=?", (chat_id,)).fetchone()
    return dict(r) if r else None


def chats_de(uid: int) -> list:
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute("SELECT chat_id, nombre, vinculado FROM telegram_chats WHERE user_id=? "
                                             "ORDER BY vinculado", (uid,))]


def desvincular(uid: int, chat_id: int) -> bool:
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM telegram_acciones WHERE chat_id=?", (chat_id,))
        return con.execute("DELETE FROM telegram_chats WHERE chat_id=? AND user_id=?", (chat_id, uid)).rowcount > 0


def _fijar_conv(chat_id: int, cid: str | None) -> None:
    with closing(db._con()) as con, con:
        con.execute("UPDATE telegram_chats SET conv_id=? WHERE chat_id=?", (cid, chat_id))


def _estado(clave: str, valor: str | None = None) -> str | None:
    with closing(db._con()) as con, con:
        if valor is not None:
            con.execute("INSERT INTO telegram_estado (clave, valor) VALUES (?,?) ON CONFLICT(clave) DO UPDATE "
                        "SET valor=excluded.valor", (clave, valor))
            return valor
        r = con.execute("SELECT valor FROM telegram_estado WHERE clave=?", (clave,)).fetchone()
    return r["valor"] if r else None


# --- Botones firmados en el servidor ------------------------------------------------------------------------
def ficha(chat_id: int, uid: int, accion: str, datos: dict | None = None, dura_s: int = 600) -> str:
    token = secrets.token_urlsafe(12)
    ahora = time.time()
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM telegram_acciones WHERE expira<?", (ahora,))
        con.execute("INSERT INTO telegram_acciones (token, chat_id, user_id, accion, datos, expira) VALUES (?,?,?,?,?,?)",
                    (token, chat_id, uid, accion, json.dumps(datos or {}), ahora + dura_s))
    return "a:" + token


def gastar_ficha(dato: str, chat_id: int, ahora: float | None = None) -> dict | None:
    """Devuelve la acción si la ficha existe, es de este chat, no ha caducado y el chat sigue vinculado
    al mismo usuario. Es de un solo uso."""
    if not isinstance(dato, str) or not dato.startswith("a:") or len(dato) > 64:
        return None
    ahora = time.time() if ahora is None else ahora
    with closing(db._con()) as con, con:
        r = con.execute("SELECT * FROM telegram_acciones WHERE token=?", (dato[2:],)).fetchone()
        if not r:
            return None
        con.execute("DELETE FROM telegram_acciones WHERE token=?", (dato[2:],))
        if r["chat_id"] != chat_id or r["expira"] < ahora:
            return None
        v = con.execute("SELECT user_id FROM telegram_chats WHERE chat_id=?", (chat_id,)).fetchone()
        if not v or v["user_id"] != r["user_id"]:
            return None
        return {"accion": r["accion"], "datos": json.loads(r["datos"]), "uid": r["user_id"]}


def teclado(*filas) -> dict:
    return {"inline_keyboard": [list(f) for f in filas]}


def boton(texto: str, dato: str) -> dict:
    return {"text": texto, "callback_data": dato}


# --- Markdown -> HTML de Telegram (todo escapado) ----------------------------------------------------------------
def _en_linea(t: str) -> str:
    partes = re.split(r"(`[^`\n]+`)", t)
    out = []
    for p in partes:
        if len(p) > 2 and p.startswith("`") and p.endswith("`"):
            out.append("<code>" + html.escape(p[1:-1]) + "</code>")
            continue
        e = html.escape(p)
        e = re.sub(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t#]*$", r"<b>\1</b>", e, flags=re.M)
        e = re.sub(r"^([ \t]*)[-*+][ \t]+", r"\1• ", e, flags=re.M)
        e = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s()]+)\)", r'<a href="\2">\1</a>', e)
        e = re.sub(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", r"<b>\1</b>", e)
        e = re.sub(r"__(?=\S)(.+?)(?<=\S)__", r"<b>\1</b>", e)
        e = re.sub(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])", r"<i>\1</i>", e)
        e = re.sub(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])", r"<i>\1</i>", e)
        e = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"<s>\1</s>", e)
        out.append(e)
    return "".join(out)


def a_html(md: str) -> str:
    """Convierte el Markdown de ARIA en el HTML limitado que admite Telegram. Todo el texto se escapa
    antes de añadir etiquetas propias; los enlaces solo pueden ser http(s)."""
    out = []
    for p in re.split(r"(```[\s\S]*?```)", md or ""):
        if len(p) >= 6 and p.startswith("```") and p.endswith("```"):
            cuerpo = re.sub(r"^[\w+-]*\n", "", p[3:-3], count=1)
            out.append("<pre>" + html.escape(cuerpo.strip("\n")) + "</pre>")
        else:
            out.append(_en_linea(p))
    return "".join(out).strip()


def trocear(texto: str, limite: int = TROZO) -> list:
    """Parte el texto en trozos de `limite` como mucho (por párrafos, líneas o palabras) sin dejar
    bloques de código abiertos entre trozos."""
    texto = (texto or "").strip()
    trozos = []
    while len(texto) > limite:
        corte = -1
        for sep in ("\n\n", "\n", " "):
            corte = texto.rfind(sep, 0, limite)
            if corte > limite // 3:
                break
        if corte <= 0:
            corte = limite
        trozos.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    if texto:
        trozos.append(texto)
    out, abierto = [], False
    for t in trozos:
        if abierto:
            t = "```\n" + t
        abierto = t.count("```") % 2 == 1
        out.append(t + ("\n```" if abierto else ""))
    return out


async def enviar_texto(b, chat_id: int, md: str, teclado_: dict | None = None) -> list:
    """Envía Markdown como HTML de Telegram, troceado. Si Telegram rechaza el HTML, se manda en texto plano."""
    enviados = []
    trozos = trocear(md) or ["…"]
    for i, t in enumerate(trozos):
        extra = {"reply_markup": teclado_} if teclado_ and i == len(trozos) - 1 else {}
        h = a_html(t)
        if len(h) > LIMITE:
            partes = trocear(t, TROZO // 2)
            enviados += [await b.llamar("sendMessage", chat_id=chat_id, text=p[:LIMITE],
                                        link_preview_options={"is_disabled": True}) for p in partes[:-1]]
            t, h = partes[-1], a_html(partes[-1])
            if len(h) > LIMITE:
                h = None
        try:
            if h is None:
                raise TelegramError(400, "demasiado largo")
            enviados.append(await b.llamar("sendMessage", chat_id=chat_id, text=h, parse_mode="HTML",
                                           link_preview_options={"is_disabled": True}, **extra))
        except TelegramError as e:
            if e.codigo != 400:
                raise
            enviados.append(await b.llamar("sendMessage", chat_id=chat_id, text=t[:LIMITE],
                                           link_preview_options={"is_disabled": True}, **extra))
    return enviados


async def enviar_html(b, chat_id: int, texto: str, teclado_: dict | None = None) -> list:
    """Envía HTML ya escapado sin volver a pasarlo por el conversor Markdown."""
    trozos, actual = [], ""
    for seccion in (texto or "").split("\n\n"):
        if actual and len(actual) + len(seccion) + 2 > LIMITE:
            trozos.append(actual)
            actual = ""
        actual += ("\n\n" if actual else "") + seccion
    if actual or not trozos:
        trozos.append(actual)
    enviados = []
    for i, trozo in enumerate(trozos):
        extra = {"reply_markup": teclado_} if teclado_ and i == len(trozos) - 1 else {}
        enviados.append(await b.llamar("sendMessage", chat_id=chat_id, text=trozo[:LIMITE], parse_mode="HTML",
                                       link_preview_options={"is_disabled": True}, **extra))
    return enviados


async def teclado_resumen(chat_id: int, u: dict) -> dict:
    """Botones bajo el resumen diario: abrir ARIA o la agenda, escucharlo y, para administradores, pausar anuncios."""
    filas = []
    if config.URL_PUBLICA:
        filas.append([{"text": "🌐 Abrir ARIA", "url": f"{config.URL_PUBLICA}/#inicio"},
                      {"text": "📅 Agenda", "url": f"{config.URL_PUBLICA}/#agenda"}])
    fila = [boton("🔊 Escuchar", await asyncio.to_thread(ficha, chat_id, u["id"], "resumen_voz", None, 86400)),
            boton("🔄 Actualizar", await asyncio.to_thread(ficha, chat_id, u["id"], "resumen_actualizar", None, 86400))]
    if u.get("rol") == "admin":
        fila.append(boton("⏸️ Pausar anuncios 30 min", await asyncio.to_thread(
            ficha, chat_id, u["id"], "pedir", {"op": "pausar", "min": 30}, 86400)))
    filas.append(fila)
    return teclado(*filas)


async def enviar_resumen(b, chat_id: int, u: dict, refrescar: bool = False) -> list:
    d = await resumen_diario.construir_resumen_diario(u, refrescar=refrescar)
    return await enviar_html(b, chat_id, resumen_diario.telegram(d), await teclado_resumen(chat_id, u))


async def enviar_briefing_voz(b, chat_id: int, u: dict) -> bool:
    """El briefing hablado como nota de voz (o, si no se puede convertir a OGG, como archivo de audio)."""
    from . import briefing_voz
    tarea = asyncio.create_task(_escribiendo(b, chat_id, "record_voice"))
    try:
        wav, _motor, _ = await briefing_voz.audio(u)
        datos, mime = await briefing_voz.ogg(wav)
    except Exception:  # noqa: BLE001 - cualquier fallo de voz: se avisa con texto y el resumen escrito sigue valiendo
        log.exception("No se pudo preparar el briefing hablado")
        return False
    finally:
        tarea.cancel()
    if mime == "audio/ogg":
        await b.subir("sendVoice", "voice", "briefing.ogg", datos, mime, chat_id=chat_id, caption="🔊 Tu briefing de hoy")
    else:
        await b.subir("sendDocument", "document", "briefing.wav", datos, mime, chat_id=chat_id, caption="🔊 Tu briefing de hoy")
    return True


async def briefing_voz_a_usuario(u: dict) -> int:
    """Envía el briefing hablado a todos los chats vinculados del usuario. Devuelve a cuántos llegó."""
    b = bot()
    if not b:
        return 0
    n = 0
    for c in await asyncio.to_thread(chats_de, u["id"]):
        try:
            n += await enviar_briefing_voz(b, c["chat_id"], u)
        except TelegramError as e:
            log.warning("Briefing hablado no enviado a un chat (%s)", e)
    return n


# --- Límites ------------------------------------------------------------------------------------------------------
_lim_mensajes = avisos.Limitador(20, 60)        # por chat vinculado
_lim_aviso_rapido = avisos.Limitador(1, 60)
_lim_desconocido = avisos.Limitador(1, 600)     # «No te conozco» como mucho 1 vez / 10 min por chat
_lim_vincular = avisos.Limitador(5, 600)        # intentos de código por chat
_lim_vincular_global = avisos.Limitador(30, 600)
_cerrojos: dict = {}


def _usuario(uid: int) -> dict | None:
    from . import usuarios
    u = usuarios.por_id(uid)
    return u if u and u["activo"] else None


# --- Proceso de actualizaciones ---------------------------------------------------------------------------------------
async def procesar(update: dict, b=None) -> None:
    b = b or bot()
    if b is None or not isinstance(update, dict):
        return
    if "callback_query" in update:
        await _callback(b, update["callback_query"])
        return
    m = update.get("message")
    if not isinstance(m, dict):
        return
    chat = m.get("chat") or {}
    if chat.get("type") != "private" or not isinstance(chat.get("id"), int):
        return  # solo chats privados (en grupos el bot no hace nada)
    chat_id = chat["id"]
    texto = m.get("text") if isinstance(m.get("text"), str) else ""
    v = await asyncio.to_thread(chat_vinculado, chat_id)
    u = await asyncio.to_thread(_usuario, v["user_id"]) if v else None
    if v and not u:  # usuario borrado o desactivado: el chat deja de valer
        await asyncio.to_thread(desvincular, v["user_id"], chat_id)
        v = None
    cmd = re.fullmatch(r"/(\w{1,32})(?:@\w+)?(?:\s+(.*))?", texto.strip(), re.S) if texto.startswith("/") else None
    if not v:
        if cmd and cmd.group(1).lower() == "start" and cmd.group(2):
            await _vincular(b, chat_id, (cmd.group(2) or "").strip(), m.get("from") or {})
        elif _lim_desconocido.permitir(chat_id):
            await b.llamar("sendMessage", chat_id=chat_id, text=NO_TE_CONOZCO)
        return
    if not _lim_mensajes.permitir(chat_id):
        if _lim_aviso_rapido.permitir(chat_id):
            await b.llamar("sendMessage", chat_id=chat_id, text="Demasiados mensajes seguidos; espera un minuto.")
        return
    if cmd:
        await _comando(b, chat_id, u, cmd.group(1).lower(), (cmd.group(2) or "").strip())
    elif enlaces.solo_url(texto):
        url = enlaces.solo_url(texto)
        f = await asyncio.to_thread(ficha, chat_id, u["id"], "resumir", {"url": url}, 3600)
        await b.llamar("sendMessage", chat_id=chat_id, text="¿Quieres que lo resuma?",
                       reply_markup=teclado([boton("Resumir", f)]))
    elif texto.strip():
        await _charlar(b, chat_id, u, texto.strip()[:MAX_TEXTO])
    elif isinstance(m.get("photo"), list) and m["photo"]:
        await _foto(b, chat_id, u, m["photo"], m.get("caption"))
    elif isinstance(m.get("document"), dict) and str(m["document"].get("mime_type", "")) in TIPOS_IMAGEN:
        await _foto(b, chat_id, u, [m["document"]], m.get("caption"))
    elif isinstance(m.get("voice"), dict):
        await _nota_de_voz(b, chat_id, u, m["voice"])
    else:
        await b.llamar("sendMessage", chat_id=chat_id, text="Por ahora solo entiendo texto, fotos y notas de voz.")


async def _vincular(b, chat_id: int, codigo: str, de: dict) -> None:
    if not _lim_vincular.permitir(chat_id) or not _lim_vincular_global.permitir("global"):
        return  # demasiados intentos: silencio (contra la fuerza bruta del código)
    nombre = " ".join(str(x) for x in (de.get("first_name"), de.get("last_name")) if x) or str(de.get("username") or "")
    uid = await asyncio.to_thread(canjear_codigo, codigo, chat_id, nombre)
    if uid is None:
        await b.llamar("sendMessage", chat_id=chat_id, text="Ese código no es válido o ha caducado. Pide otro en "
                                                              "ARIA → Ajustes → Avisos → Vincular Telegram.")
        return
    u = await asyncio.to_thread(_usuario, uid)
    await b.llamar("sendMessage", chat_id=chat_id, text=f"Hola, {u['nombre'] if u else ''}. Este chat queda vinculado "
                   "a tu cuenta de ARIA: aquí recibirás avisos y recordatorios y puedes hablar conmigo. Escribe /ayuda.")


# --- Conversación ------------------------------------------------------------------------------------------------------
async def _escribiendo(b, chat_id: int, accion: str = "typing") -> None:
    try:
        while True:
            try:
                await b.llamar("sendChatAction", chat_id=chat_id, action=accion)
            except TelegramError:
                pass
            await asyncio.sleep(4.5)
    except asyncio.CancelledError:
        pass


async def _responder(u: dict, chat_id: int, fabrica) -> tuple[str, dict | None, str | None]:
    """Recorre el generador del chat (`fabrica(cid)`) con la conversación de este chat de Telegram.
    Devuelve (respuesta en Markdown, ticket leído de una imagen o None, id de la conversación)."""
    v = await asyncio.to_thread(chat_vinculado, chat_id)
    cid = v.get("conv_id") if v else None
    nueva = not cid or not await asyncio.to_thread(db.existe, cid, u["id"])
    acumulado, error, ticket = "", None, None
    gen = fabrica(None if nueva else cid)
    try:
        async for ev in gen:
            t = ev.get("type")
            if t == "conv":
                cid = ev["id"]
                await asyncio.to_thread(_fijar_conv, chat_id, cid)
            elif t == "token":
                acumulado += ev["text"]
            elif t in ("reinicio", "herramienta"):
                acumulado = ""  # lo dicho antes de usar una herramienta no es la respuesta final
            elif t == "error":
                error = ev.get("text")
            elif t == "ticket":
                ticket = ev.get("datos")
    finally:
        await gen.aclose()
    if nueva and cid:
        conv = await asyncio.to_thread(db.obtener, cid, u["id"])
        if conv and not conv["titulo"].startswith("Telegram"):
            await asyncio.to_thread(db.renombrar, cid, u["id"], "Telegram · " + conv["titulo"])
    return acumulado.strip() or error or "No tengo respuesta ahora mismo.", ticket, cid


async def responder_chat(u: dict, chat_id: int, texto: str) -> str:
    """Pasa el mensaje por el mismo chat que la web y devuelve la respuesta final en Markdown."""
    from . import chat
    return (await _responder(u, chat_id, lambda cid: chat.conversar(u, cid, texto)))[0]


async def _charlar(b, chat_id: int, u: dict, texto: str, con_voz: bool = False) -> None:
    tarea = asyncio.create_task(_escribiendo(b, chat_id))
    try:
        respuesta = await responder_chat(u, chat_id, texto)
    finally:
        tarea.cancel()
    await enviar_texto(b, chat_id, respuesta)
    if con_voz and (await asyncio.to_thread(avisos.ajustes, u["id"]))["voz_telegram"]:
        from . import voz_puente
        audio = await voz_puente.sintetizar(respuesta, u["id"])
        if audio:
            datos, mime = audio
            if mime == "audio/ogg":
                await b.subir("sendVoice", "voice", "respuesta.ogg", datos, mime, chat_id=chat_id)
            else:
                await b.subir("sendDocument", "document", "respuesta.wav", datos, mime, chat_id=chat_id)


async def _nota_de_voz(b, chat_id: int, u: dict, voz: dict) -> None:
    from . import voz_puente
    if (voz.get("duration") or 0) > MAX_VOZ_S or (voz.get("file_size") or 0) > MAX_VOZ_BYTES:
        await b.llamar("sendMessage", chat_id=chat_id, text="La nota de voz es demasiado larga (máximo 2 minutos).")
        return
    try:
        f = await b.llamar("getFile", file_id=str(voz.get("file_id", ""))[:200])
        datos = await b.descargar(f.get("file_path", ""))
        texto = await voz_puente.transcribir(datos, str(voz.get("mime_type") or "audio/ogg"))
    except (TelegramError, voz_puente.VozError) as e:
        msg = e.args[0] if isinstance(e, voz_puente.VozError) else "No pude descargar la nota de voz."
        await b.llamar("sendMessage", chat_id=chat_id, text=msg)
        return
    texto = " ".join(texto.split())[:MAX_TEXTO]
    if not texto:
        await b.llamar("sendMessage", chat_id=chat_id, text="No he entendido la nota de voz.")
        return
    await b.llamar("sendMessage", chat_id=chat_id, text="<i>" + html.escape(texto) + "</i>", parse_mode="HTML")
    await _charlar(b, chat_id, u, texto, con_voz=True)


TIPOS_IMAGEN = ("image/jpeg", "image/png", "image/webp")


def _elegir_foto(fotos: list, maximo: int) -> dict | None:
    """La versión más grande de la foto que quepa en `maximo` bytes (Telegram manda varias, de menor a mayor)."""
    validas = [f for f in fotos if isinstance(f, dict) and f.get("file_id") and (f.get("file_size") or 0) <= maximo]
    return max(validas, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0), default=None)


async def _foto(b, chat_id: int, u: dict, fotos: list, pie) -> None:
    """Foto (con o sin pie): la mira un cerebro con visión y responde en este chat. Si es un ticket, ofrece
    «Registrar» / «Cancelar» con fichas del servidor. La imagen solo vive en memoria."""
    from . import chat, vision
    if not vision.disponible():
        await b.llamar("sendMessage", chat_id=chat_id, text=vision.NO_DISPONIBLE)
        return
    if (resto := vision.limitar(u["id"])):
        await b.llamar("sendMessage", chat_id=chat_id, text=f"Demasiadas imágenes seguidas. Espera {resto} s.")
        return
    f = _elegir_foto(fotos, vision.MAX_BYTES)
    if not f:
        await b.llamar("sendMessage", chat_id=chat_id, text="La imagen es demasiado grande (máximo 5 MB).")
        return
    try:
        info = await b.llamar("getFile", file_id=str(f.get("file_id", ""))[:200])
        datos = await b.descargar(info.get("file_path", ""), vision.MAX_BYTES)
        mime = vision.validar(datos)
    except TelegramError:
        await b.llamar("sendMessage", chat_id=chat_id, text="No pude descargar la imagen.")
        return
    except vision.VisionError as e:
        await b.llamar("sendMessage", chat_id=chat_id, text=e.mensaje)
        return
    texto = " ".join(str(pie or "").split())[:MAX_TEXTO] if isinstance(pie, str) else ""
    tarea = asyncio.create_task(_escribiendo(b, chat_id))
    try:
        respuesta, ticket, cid = await _responder(
            u, chat_id, lambda c: chat.conversar_imagen(u, c, texto, datos, mime, proponer=False))
    finally:
        tarea.cancel()
        datos = None  # noqa: F841
    kb = None
    if ticket:
        t = vision.publico(ticket)
        respuesta += (f"\n\n¿Lo apunto en tus finanzas? {t['comercio']}, {t['importe']}, {t['fecha']} "
                      f"(categoría: {t['categoria']}).")
        f_ok = await asyncio.to_thread(ficha, chat_id, u["id"], "ticket", {"ticket": ticket, "cid": cid}, 86400)
        f_no = await asyncio.to_thread(ficha, chat_id, u["id"], "cancelar", None, 86400)
        kb = teclado([boton("Registrar", f_ok), boton("Cancelar", f_no)])
    await enviar_texto(b, chat_id, respuesta, kb)


# --- Comandos ---------------------------------------------------------------------------------------------------------
def _ayuda(admin: bool) -> str:
    lineas = ["Escríbeme, mándame una nota de voz o una foto (por ejemplo, de un ticket) y te respondo como en la web. "
              "Comandos:"]
    for c, d in COMANDOS:
        if c in ("nuevovpn", "control", "informe", "reiniciar") and not admin:
            continue
        lineas.append(f"/{c} — {d}")
    return "\n".join(lineas)


def _num(v) -> str:
    return str(v).replace(".", ",")


async def texto_estado(u: dict) -> str:
    from . import services, sistema
    s = await services.estado()
    e = await asyncio.to_thread(sistema.estado)
    ok = lambda x: "funciona" if x else "NO responde"  # noqa: E731
    lineas = ["**Estado de la casa**",
              f"- SHIELD-DNS: {ok(s['shield_dns']['dns_ok'])}",
              f"- HEIMDALL (VPN): {ok(s['heimdall']['web_ok'])}"]
    r = []
    if e["temperatura"] is not None:
        r.append(f"{_num(e['temperatura'])} °C")
    if e["memoria"]:
        r.append(f"RAM {_num(e['memoria']['porcentaje'])} %")
    if e["disco"]:
        r.append(f"disco {_num(e['disco']['porcentaje'])} %")
    r.append(f"encendida desde hace {e['uptime_texto']}")
    lineas.append("- Raspberry: " + ", ".join(r))
    n = await asyncio.to_thread(avisos.no_leidos, u["id"])
    lineas.append(f"\nAvisos sin leer: {n}")
    return "\n".join(lineas)


async def _comando(b, chat_id: int, u: dict, cmd: str, arg: str) -> None:
    admin = u["rol"] == "admin"
    enviar = lambda t, k=None: enviar_texto(b, chat_id, t, k)  # noqa: E731
    if cmd in ("start", "ayuda", "help"):
        await enviar(_ayuda(admin))
    elif cmd == "nuevo":
        await asyncio.to_thread(_fijar_conv, chat_id, None)
        await enviar("Empezamos una conversación nueva.")
    elif cmd == "estado":
        await enviar(await texto_estado(u))
    elif cmd == "resumen":
        await enviar_resumen(b, chat_id, u)
    elif cmd == "tiempo":
        await enviar(await _texto_tiempo(arg))
    elif cmd == "recordatorios":
        rs = await asyncio.to_thread(recordatorios.listar, u["id"])
        if not rs:
            await enviar("No tienes recordatorios pendientes. Dime, por ejemplo, «recuérdame mañana a las 9 llamar al taller».")
        else:
            await enviar("**Tus recordatorios**\n" + "\n".join(f"- {r['id']}: {r['texto']} ({r['descripcion']})" for r in rs[:30])
                         + "\n\nPara borrar uno: «borra el recordatorio 3».")
    elif cmd == "gastos":
        await enviar(await asyncio.to_thread(_texto_gastos, u["id"]))
    elif cmd == "vpn":
        await enviar(await _texto_vpn())
    elif cmd in ("anuncios", "bloqueo"):
        await _anuncios(b, chat_id, u)
    elif cmd == "red":
        await enviar(await texto_red(u))
    elif cmd == "informe":
        if not admin:
            await enviar("Eso solo lo puede hacer un administrador.")
            return
        from . import estadisticas
        try:
            await enviar(await estadisticas.construir_informe_semanal())
        except Exception:
            await enviar("No he podido preparar el informe semanal ahora mismo.")
    elif cmd == "rutinas":
        await _rutinas(b, chat_id, u)
    elif cmd == "control":
        if not admin:
            await enviar("Eso solo lo puede hacer un administrador.")
            return
        await _control(b, chat_id, u)
    elif cmd == "nuevovpn":
        if not admin:
            await enviar("Eso solo lo puede hacer un administrador.")
            return
        from . import vpn
        partes = arg.rsplit(None, 1)
        caduca = partes[1] if len(partes) == 2 and (re.fullmatch(r"(?:24h|7d|\d{4}-\d{2}-\d{2})", partes[1], re.I) or partes[1].lower() in ("nunca", "mañana", "manana")) else None
        nombre = partes[0] if caduca else arg
        if not vpn.nombre_valido(nombre):
            await enviar("Uso: /nuevovpn <nombre> [24h|7d|AAAA-MM-DD].")
            return
        try:
            vpn.caducidad(caduca)
        except vpn.VpnError as e:
            await enviar(str(e)); return
        f_ok = await asyncio.to_thread(ficha, chat_id, u["id"], "confirmar", {"op": "nuevovpn", "nombre": nombre.strip(), "caduca": caduca})
        f_no = await asyncio.to_thread(ficha, chat_id, u["id"], "cancelar")
        await enviar(f"¿Crear el dispositivo VPN «{nombre.strip()}»" + (f" (caduca: {caduca})" if caduca else "") + "? Te enviaré su QR y el archivo .conf. Ojo: el .conf "
                     "contiene la clave privada del dispositivo; bórralo del chat cuando lo hayas importado.",
                     teclado([boton("Confirmar", f_ok), boton("Cancelar", f_no)]))
    elif cmd == "reiniciar":
        if not admin:
            await enviar("Eso solo lo puede hacer un administrador.")
            return
        f_ok = await asyncio.to_thread(ficha, chat_id, u["id"], "confirmar", {"op": "reiniciar"})
        f_no = await asyncio.to_thread(ficha, chat_id, u["id"], "cancelar")
        await enviar("¿Reiniciar la Raspberry? Se apagará en 15 segundos y ARIA volverá cuando termine.",
                     teclado([boton("✅ Sí, reiniciar", f_ok), boton("Cancelar", f_no)]))
    elif cmd == "desvincular":
        f_ok = await asyncio.to_thread(ficha, chat_id, u["id"], "confirmar", {"op": "desvincular"})
        f_no = await asyncio.to_thread(ficha, chat_id, u["id"], "cancelar")
        await enviar("¿Desvincular este chat de ARIA? Dejarás de recibir avisos aquí.",
                     teclado([boton("Confirmar", f_ok), boton("Cancelar", f_no)]))
    else:
        await enviar("No conozco ese comando. Escribe /ayuda.")


async def texto_red(u: dict) -> str:
    """Salud de la red para todos; número de dispositivos y los nuevos, solo para administradores
    (quién está en casa es privado)."""
    from . import red
    lineas = ["**La red de casa**"]
    try:
        s = await red.salud()
        lat = "; ".join(f"{d['nombre']} {_num(d['media_ms'])} ms" if d["media_ms"] is not None else f"{d['nombre']} sin respuesta"
                        for d in s["latencia"]["destinos"])
        lineas += [f"- Latencia: {lat}", f"- DNS (SHIELD): {s['dns']}", f"- VPN: {s['vpn']}"]
        if s["velocidad"]:
            v = s["velocidad"]
            lineas.append(f"- Último test de velocidad: {_num(v['bajada_mbps'])} ↓ / {_num(v['subida_mbps'])} ↑ Mbps")
    except Exception:  # noqa: BLE001 - un dato que falla no impide el resto
        log.warning("Telegram /red: no se pudo leer la salud de la red")
        lineas.append("- No he podido medir la salud de la red ahora mismo.")
    if u["rol"] != "admin":
        return "\n".join(lineas)
    try:
        ds = await red.dispositivos()
    except Exception:  # noqa: BLE001
        lineas.append("- No he podido leer los dispositivos.")
        return "\n".join(lineas)
    nuevos = [d for d in ds if not d["conocido"]]
    lineas.append(f"\nDispositivos: {len(ds)}, sin reconocer: {len(nuevos)}")
    for d in nuevos[:10]:
        lineas.append(f"- {d.get('nombre') or d.get('fabricante') or 'sin nombre'} ({d['ip']})")
    if len(nuevos) > 10:
        lineas.append(f"- … y {len(nuevos) - 10} más (míralos en ARIA → Red)")
    return "\n".join(lineas)


async def _rutinas(b, chat_id: int, u: dict) -> None:
    rs = await asyncio.to_thread(rutinas.listar, u["id"])
    if not rs:
        await enviar_texto(b, chat_id, "No tienes rutinas. Créalas en ARIA → Ajustes → Rutinas o dime, por ejemplo, "
                           "«crea una rutina que cada día a las 8 me diga el tiempo y 3 titulares».")
        return
    filas, lineas = [], ["**Tus rutinas**"]
    for r in rs:
        lineas.append(f"- {r['nombre']}: {r['descripcion']}{'' if r['activa'] else ' (EN PAUSA)'}")
        corto = r["nombre"] if len(r["nombre"]) <= 22 else r["nombre"][:21] + "…"
        f_ej = await asyncio.to_thread(ficha, chat_id, u["id"], "rutina_ejecutar", {"rid": r["id"]}, 3600)
        f_pa = await asyncio.to_thread(ficha, chat_id, u["id"], "rutina_activa", {"rid": r["id"], "activa": not r["activa"]}, 3600)
        filas.append([boton(f"Ejecutar ahora · {corto}", f_ej), boton("Reanudar" if not r["activa"] else "Pausar", f_pa)])
    await enviar_texto(b, chat_id, "\n".join(lineas), teclado(*filas))


async def _texto_tiempo(ciudad: str) -> str:
    from . import briefing
    p = await briefing.prevision(3, ciudad[:60] or None)
    if not p:
        return "No hay previsión disponible (falta ARIA_CIUDAD o no responde el servicio del tiempo)."
    et = {0: "Hoy", 1: "Mañana"}
    return f"**El tiempo en {p['ciudad']}**\n" + "\n".join(
        f"- {et.get(i, d['dia'].capitalize())}: {d['cielo']}, {d['min']}–{d['max']} °C, lluvia {d['lluvia']} %"
        for i, d in enumerate(p["dias"]))


def _texto_gastos(uid: int) -> str:
    from . import finanzas
    r = finanzas.resumen_mes(uid, None)
    if not r["movimientos"]:
        return f"No hay movimientos en {r['mes']}. Apúntalos en Finanzas o dime «he gastado 12 € en el súper»."
    cats = ", ".join(f"{c['categoria']} {finanzas.euros(c['total'])}" for c in r["categorias"][:5]) or "—"
    return (f"**Finanzas de {r['mes']}**\n- Gastos: {finanzas.euros(r['gastos'])}\n- Ingresos: {finanzas.euros(r['ingresos'])}\n"
            f"- Balance: {finanzas.euros(r['balance'])}\n- Más gasto en: {cats}")


async def _texto_vpn() -> str:
    from . import vpn
    if not vpn.configurado():
        return "HEIMDALL no está conectado a ARIA."
    try:
        cl = await vpn.listar()
    except vpn.VpnError as e:
        return str(e)
    if not cl:
        return "No hay dispositivos en la VPN."
    return "**Dispositivos de la VPN**\n" + "\n".join(
        f"- {c['nombre']}: {'conectado' if c['conectado'] else 'desconectado'}{'' if c['activo'] else ' (desactivado)'}{(' (caduca ' + c['caduca'] + ')' if c.get('caduca') else '')}"
        for c in cl)


async def _anuncios(b, chat_id: int, u: dict) -> None:
    from . import shield
    if not shield.configurado():
        await enviar_texto(b, chat_id, "SHIELD-DNS no está conectado a ARIA.")
        return
    try:
        r = await shield.resumen()
    except shield.ShieldError as e:
        await enviar_texto(b, chat_id, str(e))
        return
    t = (f"**Bloqueador de anuncios:** {'activo' if r['bloqueo_activo'] else 'EN PAUSA'}\n"
         f"Últimas 24 h: {r['consultas']} consultas, {r['bloqueadas']} bloqueadas ({_num(r['porcentaje'])} %).")
    if u["rol"] != "admin":
        await enviar_texto(b, chat_id, t)
        return
    f = [await asyncio.to_thread(ficha, chat_id, u["id"], "pedir", {"op": "pausar", "min": m}) for m in (5, 30)]
    f_r = await asyncio.to_thread(ficha, chat_id, u["id"], "reanudar")
    await enviar_texto(b, chat_id, t, teclado([boton("Pausar 5 min", f[0]), boton("Pausar 30 min", f[1])],
                                              [boton("Reanudar", f_r)]))


async def _control(b, chat_id: int, u: dict) -> None:
    """Lista los dispositivos con internet pausado o servicios bloqueados, con botones para quitar la pausa."""
    from . import control
    es = [e for e in await asyncio.to_thread(control.estado) if e["pausado"] or e["servicios_bloqueados"]]
    if not es:
        await enviar_texto(b, chat_id, "Ningún dispositivo tiene internet pausado ni servicios bloqueados ahora mismo. "
                                       "Para pausar uno, escríbeme, por ejemplo: «pausa el iPad una hora».")
        return
    filas = []
    for e in es[:20]:
        if e["pausa_manual"]:
            f = await asyncio.to_thread(ficha, chat_id, u["id"], "reanudar_control", {"clave": e["clave"]})
            filas.append([boton(f"Reanudar {e['nombre']}"[:60], f)])
        if e["servicios_manuales"]:
            f = await asyncio.to_thread(ficha, chat_id, u["id"], "desbloquear_control", {"clave": e["clave"]})
            filas.append([boton(f"Desbloquear servicios de {e['nombre']}"[:60], f)])
    await enviar_texto(b, chat_id, "**Control parental**\n" + "\n".join("- " + control.texto_estado(e) for e in es[:20])
                       + "\n\n" + control.LIMITACION_CORTA, teclado(*filas) if filas else None)


# --- Botones --------------------------------------------------------------------------------------------------------
async def _quitar_botones(b, cq: dict) -> None:
    m = cq.get("message") or {}
    try:
        await b.llamar("editMessageReplyMarkup", chat_id=m["chat"]["id"], message_id=m["message_id"],
                       reply_markup={"inline_keyboard": []})
    except (TelegramError, KeyError):
        pass


async def _callback(b, cq: dict) -> None:
    cqid = cq.get("id")
    m = cq.get("message") or {}
    chat_id = (m.get("chat") or {}).get("id")
    de = (cq.get("from") or {}).get("id")
    respuesta = "Este botón ya no sirve."
    try:
        if not isinstance(chat_id, int) or de != chat_id:
            return
        a = await asyncio.to_thread(gastar_ficha, cq.get("data"), chat_id)
        if not a:
            return
        u = await asyncio.to_thread(_usuario, a["uid"])
        if not u:
            return
        respuesta = await _accion(b, cq, chat_id, u, a["accion"], a["datos"])
    finally:
        try:
            await b.llamar("answerCallbackQuery", callback_query_id=str(cqid), text=respuesta[:190])
        except TelegramError:
            pass


async def _accion(b, cq: dict, chat_id: int, u: dict, accion: str, d: dict) -> str:
    admin = u["rol"] == "admin"
    if accion == "leido":
        await asyncio.to_thread(avisos.marcar_leido, u["id"], int(d.get("aviso", 0)))
        await _quitar_botones(b, cq)
        return "Marcado como leído."
    if accion == "posponer":
        r = await asyncio.to_thread(recordatorios.posponer, u["id"], int(d.get("rid", 0)), int(d.get("min", 10)))
        if d.get("aviso"):
            await asyncio.to_thread(avisos.marcar_leido, u["id"], int(d["aviso"]))
        await _quitar_botones(b, cq)
        return f"Te lo recuerdo {r['descripcion']}." if r else "Ese recordatorio ya no existe."
    if accion == "hecho":
        await asyncio.to_thread(recordatorios.hecho, u["id"], int(d.get("rid", 0)))
        if d.get("aviso"):
            await asyncio.to_thread(avisos.marcar_leido, u["id"], int(d["aviso"]))
        await _quitar_botones(b, cq)
        return "Hecho."
    if accion == "cancelar":
        await _quitar_botones(b, cq)
        return "Cancelado."
    if accion == "resumir":
        await _quitar_botones(b, cq)
        await _charlar(b, chat_id, u, f"Resume este enlace: {str(d.get('url', ''))[:enlaces.MAX_URL]}")
        return "Resumido."
    if accion == "rutina_ejecutar":
        r = await asyncio.to_thread(rutinas.obtener, u["id"], int(d.get("rid", 0)))
        if not r:
            return "Esa rutina ya no existe."
        tarea = asyncio.create_task(_escribiendo(b, chat_id))
        try:
            res = await rutinas.ejecutar(r, canales_=[])  # el resultado va a este chat (y a la campana)
        finally:
            tarea.cancel()
        await enviar_texto(b, chat_id, res["texto"] or "No hay resultado.")
        return "Hecho." if res["estado"] == "ok" else "No se pudo."
    if accion == "rutina_activa":
        r = await asyncio.to_thread(rutinas.actualizar, u["id"], u["rol"], int(d.get("rid", 0)), {"activa": bool(d.get("activa"))})
        if not r:
            return "Esa rutina ya no existe."
        await _quitar_botones(b, cq)
        await enviar_texto(b, chat_id, f"Rutina «{r['nombre']}» {'reanudada' if r['activa'] else 'en pausa'}.")
        return "Reanudada." if r["activa"] else "En pausa."
    if accion in ("reanudar_control", "desbloquear_control"):
        if not admin:
            return "Eso solo lo puede hacer un administrador."
        from . import control
        clave = str(d.get("clave", ""))
        if accion == "reanudar_control":
            await asyncio.to_thread(control.reanudar, clave)
        else:
            await asyncio.to_thread(control.quitar_servicios, clave)
        r = await control.reconciliar()
        await _quitar_botones(b, cq)
        fila = await asyncio.to_thread(control._fila, clave)
        await enviar_texto(b, chat_id, ("Internet reanudado en " if accion == "reanudar_control" else
                                        "Servicios desbloqueados en ") + control.nombre_de(fila) + "."
                           + ("" if r.get("ok") else f" Aún no se ha podido aplicar en SHIELD-DNS ({r.get('error')}); se reintenta solo."))
        return "Hecho."
    if accion == "ticket":  # gasto leído de una foto: se apunta en las finanzas del usuario del chat
        from . import vision
        await _quitar_botones(b, cq)
        t = d.get("ticket") if isinstance(d.get("ticket"), dict) else None
        if not t:
            return "Ese ticket ya no es válido."
        ok, texto = await vision.registrar_ticket(u, t, d.get("cid"))
        await enviar_texto(b, chat_id, texto)
        return "Apuntado." if ok else "No se pudo apuntar."
    if accion == "resumen_voz":
        ok = await enviar_briefing_voz(b, chat_id, u)
        return "Aquí lo tienes." if ok else "Ahora mismo no puedo hablar; prueba en un rato."
    if accion == "resumen_actualizar":
        await enviar_resumen(b, chat_id, u, refrescar=True)
        return "Resumen actualizado."
    if accion == "pedir":  # paso previo: se pide «Confirmar»
        if d.get("op") in OPS_ADMIN and not admin:
            return "Eso solo lo puede hacer un administrador."
        f_ok = await asyncio.to_thread(ficha, chat_id, u["id"], "confirmar", d)
        f_no = await asyncio.to_thread(ficha, chat_id, u["id"], "cancelar")
        await enviar_texto(b, chat_id, f"¿Pausar el bloqueador de anuncios {int(d.get('min', 5))} minutos?",
                           teclado([boton("Confirmar", f_ok), boton("Cancelar", f_no)]))
        return "Confirma la acción."
    if accion == "reanudar":
        if not admin:
            return "Eso solo lo puede hacer un administrador."
        from . import shield
        try:
            await shield.reanudar()
        except shield.ShieldError as e:
            return str(e)
        await enviar_texto(b, chat_id, "Bloqueador de anuncios reactivado.")
        return "Reactivado."
    if accion == "confirmar":
        op = d.get("op")
        if op in OPS_ADMIN and not admin:
            return "Eso solo lo puede hacer un administrador."
        await _quitar_botones(b, cq)
        if op == "pausar":
            from . import shield
            try:
                await shield.pausar(int(d.get("min", 5)))
            except shield.ShieldError as e:
                return str(e)
            await enviar_texto(b, chat_id, f"Bloqueador de anuncios en pausa durante {int(d.get('min', 5))} minutos.")
            return "En pausa."
        if op == "nuevovpn":
            return await _crear_vpn(b, chat_id, str(d.get("nombre", "")), d.get("caduca"))
        if op == "reiniciar":
            try:
                resultado = await asyncio.to_thread(telemetria.solicitar_reinicio)
            except RuntimeError as e:
                return str(e)
            await avisos.emitir("sistema", "aviso", f"🔄 Reiniciando la Raspberry a petición de {u['nombre']}…", "control")
            await enviar_texto(b, chat_id, "Reinicio programado. ARIA volverá en unos instantes.")
            return f"Programado en {resultado['segundos']} s."
        if op == "desvincular":
            await asyncio.to_thread(desvincular, u["id"], chat_id)
            await b.llamar("sendMessage", chat_id=chat_id, text="Chat desvinculado. ¡Hasta pronto!")
            return "Desvinculado."
    return "Acción desconocida."


def qr_png(texto: str) -> bytes:
    import qrcode
    from qrcode.image.pure import PyPNGImage
    buf = io.BytesIO()
    qrcode.make(texto, image_factory=PyPNGImage, box_size=8, border=3).save(buf)
    return buf.getvalue()


async def _crear_vpn(b, chat_id: int, nombre: str, caduca: str | None = None) -> str:
    from . import vpn
    if not vpn.nombre_valido(nombre):
        return "Nombre no válido."
    try:
        if any(c["nombre"].lower() == nombre.lower() for c in await vpn.listar()):
            await enviar_texto(b, chat_id, f"Ya existe un dispositivo llamado «{nombre}».")
            return "Ya existe."
        cid = await vpn.crear(nombre, caduca)
        conf = await vpn.configuracion(cid)
    except vpn.VpnError as e:
        await enviar_texto(b, chat_id, str(e))
        return "No se pudo crear."
    seguro = re.sub(r"[^A-Za-z0-9._-]+", "_", nombre).strip("_") or f"cliente{cid}"
    await b.subir("sendPhoto", "photo", f"{seguro}.png", await asyncio.to_thread(qr_png, conf.decode()), "image/png",
                  chat_id=chat_id, caption=f"QR de «{nombre}»: escanéalo con la app WireGuard.")
    await b.subir("sendDocument", "document", f"{seguro}.conf", conf, "application/octet-stream", chat_id=chat_id,
                  caption="Archivo .conf de WireGuard. Contiene la CLAVE PRIVADA del dispositivo: impórtalo y borra "
                          "este mensaje.")
    return "Dispositivo creado" + (f" (caduca: {caduca})." if caduca else ".")


# --- Canal del motor de avisos ------------------------------------------------------------------------------------------
async def canal(uid: int, aviso: dict) -> bool:
    b = bot()
    if b is None:
        return False
    chats = await asyncio.to_thread(chats_de, uid)
    cab = {"grave": "**Importante.** ", "aviso": "", "info": ""}.get(aviso["severidad"], "")
    enviado = False
    for c in chats:
        filas = []
        if aviso.get("recordatorio"):
            base = {"rid": aviso["recordatorio"], "aviso": aviso.get("id")}
            filas.append([boton("+10 min", await asyncio.to_thread(ficha, c["chat_id"], uid, "posponer", {**base, "min": 10}, 3 * 86400)),
                          boton("+1 h", await asyncio.to_thread(ficha, c["chat_id"], uid, "posponer", {**base, "min": 60}, 3 * 86400)),
                          boton("Hecho", await asyncio.to_thread(ficha, c["chat_id"], uid, "hecho", base, 3 * 86400))])
        elif aviso.get("id"):
            fila = [boton("Marcar como leído", await asyncio.to_thread(ficha, c["chat_id"], uid, "leido",
                                                                       {"aviso": aviso["id"]}, 7 * 86400))]
            if config.URL_PUBLICA and aviso.get("enlace"):
                fila.append({"text": "Abrir ARIA", "url": f"{config.URL_PUBLICA}/#{aviso['enlace']}"})
            filas.append(fila)
        try:
            if aviso.get("html"):
                u = await asyncio.to_thread(_usuario, uid)
                tec = await teclado_resumen(c["chat_id"], u) if u and aviso.get("tipo") == "resumen" else (teclado(*filas) if filas else None)
                await enviar_html(b, c["chat_id"], aviso["html"], tec)
            else:
                await enviar_texto(b, c["chat_id"], cab + aviso["texto"], teclado(*filas) if filas else None)
            enviado = True
        except TelegramError as e:
            log.warning("No se pudo enviar el aviso por Telegram (%s)", e.codigo)
    return enviado


# --- Bucle de long polling ------------------------------------------------------------------------------------------
_semaforo = asyncio.Semaphore(4)


async def _procesar_seguro(update: dict) -> None:
    chat_id = ((update.get("message") or {}).get("chat") or {}).get("id") or \
        (((update.get("callback_query") or {}).get("message") or {}).get("chat") or {}).get("id")
    cerrojo = _cerrojos.setdefault(chat_id, asyncio.Lock())
    async with _semaforo, cerrojo:
        try:
            await procesar(update)
        except TelegramError as e:
            log.warning("Telegram: error al responder (%s)", e.codigo)
        except Exception:  # noqa: BLE001 - un mensaje raro no debe tumbar el bot
            log.exception("Telegram: fallo procesando una actualización")
    if len(_cerrojos) > 500:
        _cerrojos.clear()


async def preparar(b) -> bool:
    try:
        _yo.update(await b.llamar("getMe"))
        info = await b.llamar("getWebhookInfo")
        if info.get("url"):  # con webhook no funciona getUpdates
            await b.llamar("deleteWebhook")
        await b.llamar("setMyCommands", commands=[{"command": c, "description": d} for c, d in COMANDOS])
    except TelegramError as e:
        log.warning("Telegram: no se pudo preparar el bot (%s %s)", e.codigo, e.descripcion)
        return False
    log.info("Telegram: bot @%s listo (long polling)", _yo.get("username"))
    return True


async def bucle() -> None:
    b = bot()
    if b is None:
        return
    while not await preparar(b):
        await asyncio.sleep(600)
    offset = int(await asyncio.to_thread(_estado, "offset") or 0)
    while True:
        try:
            ups = await b.llamar("getUpdates", espera=65, offset=offset, timeout=50,
                                 allowed_updates=["message", "callback_query"])
        except asyncio.CancelledError:
            raise
        except TelegramError as e:
            espera = 600 if e.codigo == 401 else 30 if e.codigo == 409 else 5
            log.warning("Telegram: getUpdates falló (%s); reintento en %d s", e.codigo, espera)
            await asyncio.sleep(espera)
            continue
        for u in ups or []:
            offset = max(offset, int(u.get("update_id", 0)) + 1)
            asyncio.create_task(_procesar_seguro(u))
        if ups:
            await asyncio.to_thread(_estado, "offset", str(offset))


async def probar() -> int:
    if not configurado():
        print("TELEGRAM_BOT_TOKEN está vacío en .env: el bot está apagado.")
        return 1
    try:
        yo = await bot().llamar("getMe")
    except TelegramError as e:
        print(f"El token no funciona ({e.codigo}: {e.descripcion}).")
        return 1
    print(f"Token válido. Bot: @{yo.get('username')} (id {yo.get('id')}). Enlace: https://t.me/{yo.get('username')}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    if "--probar" in sys.argv:
        sys.exit(asyncio.run(probar()))
    print("Uso: python -m aria.telegram --probar")
