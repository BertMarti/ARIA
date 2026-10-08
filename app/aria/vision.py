"""Visión: ARIA mira una foto (chat web o Telegram) y responde sobre ella.

- Proveedores gratuitos en la nube, compatibles con OpenAI: Gemini (principal) y Groq (respaldo). Nunca el
  modelo local (el 3B no ve imágenes). Si ninguno está disponible, se responde con un mensaje claro.
- La imagen solo vive en memoria durante la petición: nunca se escribe en disco ni en la base de datos (el
  historial guarda «[imagen]» y el texto que produjo el modelo). Antes de enviarla se valida el tipo por sus
  bytes (JPEG/PNG/WebP), el tamaño (≤ 5 MB) y se le quitan los metadatos (EXIF/GPS, XMP, IPTC, comentarios)
  sin dependencias nuevas.
- Tickets: si la imagen es un ticket o factura (o el usuario lo pide), el modelo añade un bloque «ticket» con
  comercio, fecha, total y categoría. ARIA lo propone y el usuario lo confirma con un botón; se apunta con la
  herramienta `registrar_movimiento` del usuario de la sesión (el uid lo pone siempre el servidor).
"""
import base64
import binascii
import json
import logging
import os
import re
import secrets
import time

import httpx

from . import cerebros, config, db, finanzas, tiempo, tools
from .voz import Limitador

log = logging.getLogger("aria.vision")

MAX_BYTES = 5 * 1024 * 1024
MAX_TEXTO = 2000
MAX_TOKENS = 1200
TIMEOUT_S = 45
TICKET_S = 30 * 60          # una propuesta de ticket caduca a los 30 min
MAX_TICKETS_USUARIO = 20

NO_DISPONIBLE = ("Ahora mismo no puedo ver imágenes: no hay ningún servicio de visión disponible "
                 "(Gemini o Groq). Inténtalo más tarde o descríbemela con palabras.")

limite_minuto = Limitador(int(os.environ.get("ARIA_VISION_MINUTO", "6")), 60)
limite_hora = Limitador(int(os.environ.get("ARIA_VISION_HORA", "60")), 3600)


class VisionError(Exception):
    def __init__(self, estado: int, mensaje: str):
        super().__init__(mensaje)
        self.estado, self.mensaje = estado, mensaje


def limitar(uid) -> int:
    """0 si el usuario puede mandar otra imagen; si no, segundos que faltan."""
    return limite_minuto.esperar(uid) or limite_hora.esperar(uid)


# --- Validación y limpieza de la imagen ------------------------------------------------------------
def tipo(datos: bytes) -> str | None:
    """Tipo real por los primeros bytes (nunca por lo que diga el cliente)."""
    if datos[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(datos) >= 12 and datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    return None


def validar(datos: bytes) -> str:
    """Devuelve el tipo MIME o lanza VisionError (400/413/415)."""
    if not datos:
        raise VisionError(400, "No llegó ninguna imagen.")
    if len(datos) > MAX_BYTES:
        raise VisionError(413, "La imagen es demasiado grande (máximo 5 MB).")
    mime = tipo(datos)
    if not mime:
        raise VisionError(415, "Solo puedo ver imágenes JPEG, PNG o WebP.")
    return mime


def desde_data_url(valor) -> tuple[bytes, str]:
    """«data:image/…;base64,…» del navegador -> (bytes, tipo real)."""
    if not isinstance(valor, str):
        raise VisionError(400, "Imagen no válida.")
    m = re.fullmatch(r"data:image/[\w.+-]{1,20};base64,([A-Za-z0-9+/=\s]+)", valor[:MAX_BYTES * 2])
    if not m:
        raise VisionError(415, "Solo puedo ver imágenes JPEG, PNG o WebP.")
    b64 = m.group(1)
    if len(b64) * 3 // 4 > MAX_BYTES + 3:
        raise VisionError(413, "La imagen es demasiado grande (máximo 5 MB).")
    try:
        datos = base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        raise VisionError(400, "Imagen no válida.") from None
    return datos, validar(datos)


def _jpeg_sin_metadatos(d: bytes) -> bytes:
    """Quita APP1 (EXIF/GPS, XMP), APP13 (IPTC), comentarios y demás APPn; conserva JFIF, ICC y Adobe."""
    out, i = bytearray(d[:2]), 2
    while i + 4 <= len(d):
        if d[i] != 0xFF:
            raise VisionError(415, "La imagen JPEG está dañada.")
        marca = d[i + 1]
        if marca == 0xFF:  # bytes de relleno
            i += 1
            continue
        if marca == 0xDA:  # inicio de los datos de la imagen: el resto se copia tal cual
            out += d[i:]
            return bytes(out)
        if marca == 0x01 or 0xD0 <= marca <= 0xD8:
            out += d[i:i + 2]
            i += 2
            continue
        largo = int.from_bytes(d[i + 2:i + 4], "big")
        if largo < 2 or i + 2 + largo > len(d):
            raise VisionError(415, "La imagen JPEG está dañada.")
        seg = d[i:i + 2 + largo]
        icc = marca == 0xE2 and seg[4:16] == b"ICC_PROFILE\x00"
        quitar = marca == 0xFE or (0xE1 <= marca <= 0xEF and marca != 0xEE and not icc)
        if not quitar:
            out += seg
        i += 2 + largo
    raise VisionError(415, "La imagen JPEG está incompleta.")


_PNG_FUERA = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}


def _png_sin_metadatos(d: bytes) -> bytes:
    out, i = bytearray(d[:8]), 8
    while i + 12 <= len(d):
        largo = int.from_bytes(d[i:i + 4], "big")
        nombre = d[i + 4:i + 8]
        fin = i + 12 + largo
        if fin > len(d):
            raise VisionError(415, "La imagen PNG está dañada.")
        if nombre not in _PNG_FUERA:
            out += d[i:fin]
        i = fin
        if nombre == b"IEND":
            return bytes(out)
    raise VisionError(415, "La imagen PNG está incompleta.")


def _webp_sin_metadatos(d: bytes) -> bytes:
    trozos, i = [], 12
    while i + 8 <= len(d):
        nombre = d[i:i + 4]
        largo = int.from_bytes(d[i + 4:i + 8], "little")
        fin = i + 8 + largo + (largo & 1)
        if i + 8 + largo > len(d):
            raise VisionError(415, "La imagen WebP está dañada.")
        if nombre not in (b"EXIF", b"XMP "):
            t = bytearray(d[i:min(fin, len(d))])
            if nombre == b"VP8X" and len(t) > 8:
                t[8] &= ~0x0C & 0xFF  # sin las marcas de EXIF (0x08) y XMP (0x04)
            trozos.append(bytes(t))
        i = fin
    cuerpo = b"WEBP" + b"".join(trozos)
    return b"RIFF" + len(cuerpo).to_bytes(4, "little") + cuerpo


def sin_metadatos(datos: bytes, mime: str) -> bytes:
    """Copia de la imagen sin metadatos (ubicación GPS, cámara, fecha…). No se recodifica: no hace falta Pillow."""
    if mime == "image/jpeg":
        return _jpeg_sin_metadatos(datos)
    if mime == "image/png":
        return _png_sin_metadatos(datos)
    if mime == "image/webp":
        return _webp_sin_metadatos(datos)
    raise VisionError(415, "Solo puedo ver imágenes JPEG, PNG o WebP.")


# --- Proveedores --------------------------------------------------------------------------------------
class Proveedor:
    def __init__(self, id, nombre, url, var_clave, var_modelo, modelo_defecto):
        self.id, self.nombre, self.url = id, nombre, url
        self.var_clave, self.var_modelo, self.modelo_defecto = var_clave, var_modelo, modelo_defecto

    def modelo(self) -> str:
        return os.environ.get(self.var_modelo, "").strip() or self.modelo_defecto

    def clave(self) -> str:
        return os.environ.get(self.var_clave, "").strip()

    def etiqueta(self) -> str:
        return f"{self.nombre} · {self.modelo()} (visión)"

    @property
    def espera_id(self) -> str:
        return "vision_" + self.id


PROVEEDORES = {p.id: p for p in (
    Proveedor("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
              "GEMINI_API_KEY", "ARIA_MODELO_VISION_GEMINI", "gemini-3.5-flash-lite"),
    Proveedor("groq", "Groq", "https://api.groq.com/openai/v1/chat/completions",
              "GROQ_API_KEY", "ARIA_MODELO_VISION_GROQ", "qwen/qwen3.8-27b"),
)}
ORDEN_DEFECTO = "gemini,groq"


def orden() -> list:
    """Proveedores configurados (ARIA_VISION; «no» la apaga), en orden y con clave."""
    v = os.environ.get("ARIA_VISION", ORDEN_DEFECTO).strip().lower()
    if v in ("no", "0", "off", "ninguno"):
        return []
    ids = [i.strip() for i in (v or ORDEN_DEFECTO).split(",")]
    return [PROVEEDORES[i] for i in dict.fromkeys(ids) if i in PROVEEDORES and PROVEEDORES[i].clave()]


def disponible() -> bool:
    return bool(orden())


def cadena() -> list:
    return [p for p in orden() if not cerebros.en_espera(p.espera_id)]


# --- Prompt y respuesta -----------------------------------------------------------------------------
_PIDE_APUNTAR = re.compile(r"\b(apunt\w*|registr\w*|anot\w*|gasto|gastos|ticket|tique|factura|recibo|finanzas)\b", re.I)


def _sistema(nombre: str, categorias: list, pide_apuntar: bool) -> str:
    hoy = tiempo.ahora()
    fecha = f"{tools.DIAS[hoy.weekday()]} {hoy.day} de {tools.MESES[hoy.month - 1]} de {hoy.year}"
    return (
        f"Eres ARIA, la asistente de casa de {nombre or 'tu usuario'}. Hoy es {fecha} ({hoy.date().isoformat()}). "
        "Te envían una imagen. Responde siempre en español de España, de forma breve y clara, a lo que se "
        "pregunta sobre ella; si no se pregunta nada, describe lo importante. No inventes lo que no se ve o "
        "no se lee bien: dilo. Usa Markdown sencillo.\n"
        "Si la imagen es un ticket de compra, una factura o un recibo"
        + (" (el usuario quiere apuntar el gasto)" if pide_apuntar else "")
        + ", resume comercio, fecha, total y categoría, y AÑADE al final un bloque exactamente así:\n"
        "```ticket\n{\"comercio\": \"Nombre del comercio\", \"fecha\": \"AAAA-MM-DD\", \"total\": 12.34, "
        "\"categoria\": \"Supermercado\"}\n```\n"
        "«total» es el importe final pagado en euros (número con punto decimal). «categoria» debe ser una de: "
        + ", ".join(categorias) + ". Si la fecha no se lee, usa null. Si no es un ticket, no añadas el bloque. "
        "Tú NO apuntas nada: nunca digas «hecho», «apuntado» ni «registrado»; el usuario lo confirmará con un "
        "botón debajo de tu respuesta.")


_BLOQUE = re.compile(r"```\s*(?:ticket|json)?\s*(\{[^`]*?\})\s*```", re.S)


def extraer_ticket(texto: str, uid: int | None) -> tuple[str, dict | None]:
    """Quita el bloque «ticket» del texto y lo valida. Devuelve (texto limpio, ticket o None)."""
    ticket = None
    for m in _BLOQUE.finditer(texto or ""):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(d, dict) and "total" in d:
            ticket = d
            texto = texto.replace(m.group(0), "")
            break
    texto = re.sub(r"\n{3,}", "\n\n", (texto or "").strip())
    if not ticket:
        return texto, None
    try:
        comercio = " ".join(str(ticket.get("comercio") or "").split())[:80] or "Ticket"
        total = finanzas.a_centimos(ticket.get("total"))
        total = abs(total)
        try:
            fecha = finanzas.fecha_valida(ticket.get("fecha"))
        except finanzas.FinanzasError:
            fecha = tiempo.ahora().date().isoformat()
        categoria = None
        if ticket.get("categoria") and uid is not None:
            existentes = {c.lower(): c for c in finanzas.categorias(uid)}
            categoria = existentes.get(str(ticket["categoria"]).strip().lower())
    except (finanzas.FinanzasError, TypeError, ValueError):
        return texto, None
    return texto, {"comercio": comercio, "fecha": fecha, "total": total, "categoria": categoria}


def publico(t: dict) -> dict:
    """Datos del ticket para mostrar (sin nada interno)."""
    return {"comercio": t["comercio"], "fecha": t["fecha"], "total": t["total"],
            "importe": finanzas.euros(t["total"]), "categoria": t["categoria"] or "automática"}


def _contenido(r: dict) -> str:
    try:
        c = r["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""
    if isinstance(c, list):  # algunas APIs devuelven trozos
        c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
    c = re.sub(r"<think>.*?</think>", "", str(c or ""), flags=re.S)
    return c.strip()


async def _llamar(p: Proveedor, cuerpo: dict) -> str:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S, connect=5)) as c:
            r = await c.post(p.url, json=cuerpo, headers={"Authorization": f"Bearer {p.clave()}"})
    except httpx.HTTPError as e:
        raise cerebros._error_httpx(e) from None
    if r.status_code != 200:
        raise cerebros.clasificar_http(r.status_code, dict(r.headers), r.text[:2000])
    try:
        texto = _contenido(r.json())
    except ValueError:
        raise cerebros.ProveedorError("http", "respuesta no válida") from None
    if not texto:
        raise cerebros.ProveedorError("http", "respuesta vacía")
    return texto


async def analizar(datos: bytes, mime: str, pregunta: str, usuario: dict, historial: list | None = None) -> dict:
    """Pregunta a los proveedores de visión (en orden) por la imagen.

    Devuelve {"texto", "ticket" (o None), "proveedor", "modelo", "etiqueta"}. Lanza VisionError si ninguno puede."""
    if not orden():
        raise VisionError(503, NO_DISPONIBLE)
    limpia = sin_metadatos(datos, mime)
    url = f"data:{mime};base64," + base64.b64encode(limpia).decode()
    del limpia
    pregunta = (pregunta or "").strip()[:MAX_TEXTO]
    uid = usuario.get("id")
    cats = finanzas.categorias(uid) if uid is not None else list(finanzas.CATEGORIAS_DEFECTO)
    previos = [{"role": m["role"], "content": str(m["content"])[:1500]} for m in (historial or [])[-6:]
               if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]
    mensajes = [{"role": "system", "content": _sistema(usuario.get("nombre") or config.NOMBRE_USUARIO, cats,
                                                       bool(_PIDE_APUNTAR.search(pregunta)))}]
    mensajes += previos
    mensajes.append({"role": "user", "content": [
        {"type": "text", "text": pregunta or "¿Qué ves en esta imagen?"},
        {"type": "image_url", "image_url": {"url": url}}]})
    ultimo = None
    for p in cadena():
        cuerpo = {"model": p.modelo(), "messages": mensajes, "max_tokens": MAX_TOKENS, "temperature": 0.2,
                  "stream": False}
        t0 = time.perf_counter()
        try:
            texto = await _llamar(p, cuerpo)
        except cerebros.ProveedorError as e:
            ultimo = e
            cerebros.registrar_fallo(p.espera_id, e)
            log.warning("Visión: %s falló (%s)", p.nombre, e.tipo)  # sin imagen ni texto en el registro
            continue
        cerebros.limpiar_espera(p.espera_id)
        log.info("Visión: %s respondió en %.1f s", p.nombre, time.perf_counter() - t0)
        limpio, ticket = extraer_ticket(texto, uid)
        return {"texto": limpio or "No he sabido interpretar la imagen.", "ticket": ticket, "proveedor": p.id,
                "modelo": p.modelo(), "etiqueta": p.etiqueta()}
    esperas = [cerebros.en_espera(p.espera_id) for p in orden()]
    if (ultimo and ultimo.tipo == "cuota") or any(e and e[1] == "cuota" for e in esperas):
        raise VisionError(429, "He agotado por ahora el límite gratuito para ver imágenes. Prueba dentro de un rato.")
    raise VisionError(503, NO_DISPONIBLE)


# --- Propuestas de ticket (chat web): en memoria, ligadas al usuario y de un solo uso ---------------------
_tickets: dict = {}  # token -> {"uid", "ticket", "cid", "expira"}
_ahora = time.time


def proponer(uid: int, ticket: dict, cid: str | None = None) -> str:
    ahora = _ahora()
    for k in [k for k, v in _tickets.items() if v["expira"] < ahora]:
        _tickets.pop(k, None)
    mios = sorted((v["expira"], k) for k, v in _tickets.items() if v["uid"] == uid)
    for _, k in mios[:max(0, len(mios) - MAX_TICKETS_USUARIO + 1)]:
        _tickets.pop(k, None)
    token = secrets.token_urlsafe(18)
    _tickets[token] = {"uid": uid, "ticket": dict(ticket), "cid": cid, "expira": ahora + TICKET_S}
    return token


def tomar(uid: int, token: str) -> dict | None:
    """La propuesta si es de este usuario y no ha caducado (y se gasta). La de otro usuario ni se toca."""
    v = _tickets.get(token) if isinstance(token, str) else None
    if not v or v["uid"] != uid:
        return None
    _tickets.pop(token, None)
    return v if v["expira"] >= _ahora() else None


async def registrar_ticket(usuario: dict, ticket: dict, cid: str | None = None) -> tuple[bool, str]:
    """Apunta el gasto con la herramienta de finanzas del usuario (rol y uid de la sesión, nunca del modelo)."""
    args = {"concepto": ticket["comercio"], "importe": -abs(int(ticket["total"])) / 100, "fecha": ticket["fecha"]}
    if ticket.get("categoria"):
        args["categoria"] = ticket["categoria"]
    res = await tools.ejecutar("registrar_movimiento", args, usuario["rol"], uid=usuario["id"])
    ok = res.startswith("Apuntado")
    if ok and cid and db.existe(cid, usuario["id"]):
        db.anadir(cid, "assistant", res, "Finanzas", "finanzas")
    return ok, res
