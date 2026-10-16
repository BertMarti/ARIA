"""Puente efímero navegador -> tele. Los archivos nunca pasan por el disco de ARIA."""
import asyncio
import html
import ipaddress
import json
import re
import secrets
import socket
import struct
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import quote, urljoin, urlparse

import httpx

from . import config, red, registro

MAX_VIDEO = 200 * 1024 ** 3
TROZO = 1024 ** 2
CADUCIDAD = 12 * 3600
_HEX = re.compile(r"^[0-9a-fA-F]{64}$")


class TeleError(Exception):
    pass


@dataclass
class Token:
    valor: str
    huella: str
    uid: int
    tamano: int
    mime: str
    nombre: str
    sesion: "Sesion"
    creado: float = field(default_factory=time.time)


class Sesion:
    def __init__(self, ws, uid):
        self.ws, self.uid = ws, uid
        self.tokens = {}
        self.pendientes = {}
        self.inflight = 0
        self.siguiente = 1
        self.send_lock = asyncio.Lock()

    async def enviar(self, dato):
        async with self.send_lock:
            await self.ws.send_json(dato)


_sesiones: dict[int, set[Sesion]] = {}
_tokens: dict[str, Token] = {}
_dispositivos = {}
_cache_dispositivos = (0.0, [])
_chromecasts = {}


def limpiar():
    ahora = time.time()
    for token, dato in list(_tokens.items()):
        if ahora - dato.creado > CADUCIDAD:
            _tokens.pop(token, None)
            dato.sesion.tokens.pop(token, None)


def _huella(v):
    return isinstance(v, str) and bool(_HEX.fullmatch(v))


def _nombre(v):
    return isinstance(v, str) and 0 < len(v) <= 200 and "\x00" not in v


def en_red(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(config.RED_PERMITIDA, strict=False)
    except ValueError:
        return False


def _destino(ip):
    if not isinstance(ip, str) or not en_red(ip) or ip == config.LAN_IP:
        raise TeleError("La IP no pertenece a la red permitida.")
    return ip


async def ofrecer(sesion: Sesion, d: dict, subtitulos=False):
    limpiar()
    huella, nombre = d.get("huella"), d.get("nombre", "subtitulos.vtt" if subtitulos else "")
    tamano = d.get("tamano")
    if not _huella(huella) or not _nombre(nombre) or not isinstance(tamano, int) or not 0 < tamano <= MAX_VIDEO:
        raise TeleError("Oferta no válida.")
    mime = "text/vtt" if subtitulos else (d.get("mime") if isinstance(d.get("mime"), str) else "")
    mime = mime[:120] or "application/octet-stream"
    token = secrets.token_urlsafe(24)
    dato = Token(token, huella.lower(), sesion.uid, tamano, mime, nombre, sesion)
    sesion.tokens[token] = dato
    _tokens[token] = dato
    seguro = re.sub(r"[^A-Za-z0-9._-]", "_", nombre)[:200]
    return {"tipo": "ofrecido", "huella": huella, "token": token,
            "url": f"http://{config.LAN_IP}:8095/flujo/{token}/{seguro}"}


async def trozo(dato: Token, inicio: int, fin: int) -> bytes:
    s = dato.sesion
    if s.inflight >= 4 or fin < inicio or fin - inicio + 1 > TROZO:
        raise TeleError("Demasiadas peticiones de trozos.")
    ident = s.siguiente
    s.siguiente += 1
    fut = asyncio.get_running_loop().create_future()
    s.pendientes[ident] = (fut, fin - inicio + 1)
    s.inflight += 1
    try:
        await s.enviar({"tipo": "pedir", "id": ident, "huella": dato.huella,
                        "inicio": inicio, "fin": fin})
        return await asyncio.wait_for(fut, 20)
    finally:
        s.inflight -= 1
        s.pendientes.pop(ident, None)


def url_flujo(dato: Token) -> str:
    """URL que pide la tele (nombre codificado: espacios y tildes rompen la URL)."""
    return f"http://{config.LAN_IP}:8095/flujo/{dato.valor}/{quote(dato.nombre)}"


def didl(dato: Token, uri: str, titulo: str) -> str:
    """Metadatos DIDL-Lite completos: muchas teles (Android TV, Samsung, LG) rechazan con 500 los mínimos."""
    mime = mime_cast(dato) if dato.mime in ("", "application/octet-stream", "video/x-matroska") else dato.mime
    clase = "object.item.audioItem.musicTrack" if mime.startswith("audio/") else "object.item.videoItem"
    flags = "DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"
    return ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"><item id="0" parentID="-1" restricted="1">'
            f"<dc:title>{html.escape(titulo[:200])}</dc:title><upnp:class>{clase}</upnp:class>"
            f'<res protocolInfo="http-get:*:{html.escape(mime)}:{flags}" size="{dato.tamano}">{html.escape(uri)}</res>'
            "</item></DIDL-Lite>")


RECEPTOR_CAST = "CC1AD845"   # Default Media Receiver de Google Cast (el que usa Chrome para vídeos)


def abrir_receptor(cast, espera=15) -> None:
    """Síncrono (va en un hilo): lanza el receptor estándar y espera a que esté activo."""
    if cast.app_id != RECEPTOR_CAST:
        cast.start_app(RECEPTOR_CAST)
        limite = time.time() + espera
        while cast.app_id != RECEPTOR_CAST and time.time() < limite:
            time.sleep(.3)
    if cast.app_id != RECEPTOR_CAST:
        raise TeleError("La tele no ha abierto el reproductor de Cast.")


def mime_cast(dato: Token) -> str:
    """El receptor de Google Cast no acepta video/x-matroska ni tipos vacíos: MKV y desconocidos van como MP4."""
    if dato.mime.startswith(("video/mp4", "video/webm", "audio/", "application/x-mpegurl")):
        return dato.mime
    return "video/mp4"


def validar_token(valor: str) -> Token | None:
    limpiar()
    dato = _tokens.get(valor)
    return dato if dato and secrets.compare_digest(dato.valor, valor) else None


async def canal(ws, usuario):
    uid = usuario["id"]
    if len(_sesiones.get(uid, set())) >= 3:
        await ws.close(code=1013)
        return
    s = Sesion(ws, uid)
    _sesiones.setdefault(uid, set()).add(s)
    await ws.accept()
    try:
        while True:
            mensaje = await ws.receive()
            if mensaje.get("type") == "websocket.disconnect":
                break
            if mensaje.get("bytes") is not None:
                b = mensaje["bytes"]
                if len(b) < 4:
                    continue
                ident = struct.unpack(">I", b[:4])[0]
                pendiente = s.pendientes.get(ident)
                if pendiente:
                    fut, maximo = pendiente
                else:
                    fut, maximo = None, 0
                if fut and len(b) - 4 == maximo and len(b) - 4 <= TROZO and not fut.done():
                    fut.set_result(b[4:])
                elif fut and not fut.done():
                    fut.set_exception(TeleError("El navegador entregó un trozo incompleto."))
                continue
            try:
                d = json.loads(mensaje.get("text", "{}"))
            except (TypeError, ValueError):
                continue
            if d.get("tipo") == "ofrecer":
                try:
                    await s.enviar(await ofrecer(s, d))
                except TeleError as e:
                    await s.enviar({"tipo": "error", "error": str(e)})
            elif d.get("tipo") == "subtitulos":
                try:
                    await s.enviar(await ofrecer(s, {**d, "nombre": "subtitulos.vtt", "mime": "text/vtt"}, True))
                except TeleError as e:
                    await s.enviar({"tipo": "error", "error": str(e)})
            elif d.get("tipo") == "error" and isinstance(d.get("id"), int):
                pendiente = s.pendientes.get(d["id"])
                fut = pendiente[0] if pendiente else None
                if fut and not fut.done():
                    fut.set_exception(TeleError("El navegador no pudo leer el archivo."))
    finally:
        for fut, _ in s.pendientes.values():
            if not fut.done():
                fut.set_exception(TeleError("Canal cerrado."))
        for token in list(s.tokens):
            _tokens.pop(token, None)
        _sesiones[uid].discard(s)
        if not _sesiones[uid]:
            _sesiones.pop(uid, None)


async def flujo(token, rango=None):
    dato = validar_token(token)
    if not dato:
        raise TeleError("no encontrado")
    inicio, fin = rango or (0, dato.tamano - 1)
    async def generar():
        for pos in range(inicio, fin + 1, TROZO):
            yield await trozo(dato, pos, min(fin, pos + TROZO - 1))
    return dato, generar()


async def descubrir():
    global _cache_dispositivos
    try:
        archivo = config.DESCUBRE_DIR / "dispositivos.json"
        dato = json.loads(archivo.read_text(encoding="utf-8"))
        if time.time() - float(dato.get("ts", 0)) < 60:
            lista = [d for d in dato.get("dispositivos", []) if isinstance(d, dict) and en_red(d.get("ip", ""))]
            _cache_dispositivos = (time.monotonic(), lista)
            return lista
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    ahora = time.monotonic()
    for identificador, (cast, ultimo) in list(_chromecasts.items()):
        if ahora - ultimo > 2 * 3600:
            await asyncio.to_thread(cast.disconnect)
            _chromecasts.pop(identificador, None)
    if time.monotonic() - _cache_dispositivos[0] < 60:
        return _cache_dispositivos[1]
    candidatos = await red.dispositivos()
    ips = {d.get("ip") for d in candidatos if isinstance(d, dict) and en_red(d.get("ip", ""))}
    resultado = await asyncio.gather(*(_chromecast(ip) for ip in ips), *(_dlna(ip) for ip in ips), return_exceptions=True)
    vistos = {}
    for d in resultado:
        if isinstance(d, dict):
            vistos[d["id"]] = d
    vistos.update(_dispositivos)
    _cache_dispositivos = (time.monotonic(), list(vistos.values()))
    return _cache_dispositivos[1]


async def _chromecast(ip):
    try:
        async with httpx.AsyncClient(timeout=1.2) as c:
            r = await c.get(f"http://{ip}:8008/setup/eureka_info")
            if r.is_success:
                return {"id": f"cast:{ip}", "nombre": r.json().get("name") or ip, "modelo": "", "tipo": "chromecast",
                        "ip": ip, "puerto": 8009, "video": True, "grupo": False, "control": None}
    except (httpx.HTTPError, ValueError):
        pass
    return None


async def _dlna(ip):
    mensaje = ("M-SEARCH * HTTP/1.1\r\nHOST: %s:1900\r\nMAN: \"ssdp:discover\"\r\n"
               "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\nMX: 1\r\n\r\n") % ip
    class Protocolo(asyncio.DatagramProtocol):
        def __init__(self):
            self.futuro = asyncio.get_running_loop().create_future()

        def datagram_received(self, datos, _direccion):
            if not self.futuro.done():
                self.futuro.set_result(datos)

        def error_received(self, error):
            if not self.futuro.done():
                self.futuro.set_exception(error)

    try:
        bucle = asyncio.get_running_loop()
        transporte, protocolo = await bucle.create_datagram_endpoint(
            Protocolo, remote_addr=(ip, 1900))
        try:
            transporte.sendto(mensaje.encode())
            datos = await asyncio.wait_for(protocolo.futuro, 1.5)
        finally:
            transporte.close()
        cab = {}
        for linea in datos.decode(errors="ignore").splitlines()[1:]:
            if ":" in linea:
                clave, valor = linea.split(":", 1)
                cab[clave.lower()] = valor.strip()
        location = cab.get("location")
        if not _url_de_tele(location, ip) or not en_red(ip):
            return None
        xml = await _xml(location)
        nombre = next((x.text for x in xml.iter() if x.tag.endswith("friendlyName")), ip)
        control = None
        for servicio in xml.iter():
            if not servicio.tag.endswith("service"):
                continue
            tipo = next((x.text or "" for x in servicio if x.tag.endswith("serviceType")), "")
            if "AVTransport" in tipo:
                control = next((x.text for x in servicio if x.tag.endswith("controlURL")), None)
                break
        control_url = urljoin(location, control) if control else None
        if control_url and _url_de_tele(control_url, ip):
            return {"id": f"dlna:{ip}", "nombre": nombre, "tipo": "dlna", "ip": ip,
                    "control": control_url}
    except (OSError, asyncio.TimeoutError, UnicodeError, ValueError, ET.ParseError, httpx.HTTPError):
        pass
    return None


def _url_de_tele(url, ip):
    try:
        dato = urlparse(url)
        return (dato.scheme == "http" and dato.hostname == ip and
                1 <= (dato.port or 80) <= 65535)
    except (TypeError, ValueError):
        return False


async def _xml(url):
    async with httpx.AsyncClient(timeout=1.5, follow_redirects=False) as c:
        r = await c.get(url)
        if len(r.content) > 256 * 1024 or b"<!DOCTYPE" in r.content.upper():
            raise TeleError("XML no permitido")
        return ET.fromstring(r.content)


def soap(control, accion, argumentos=""):
    acciones = {"SetAVTransportURI": "u:SetAVTransportURI", "Play": "u:Play", "Pause": "u:Pause",
                "Stop": "u:Stop", "Seek": "u:Seek", "GetPositionInfo": "u:GetPositionInfo"}
    if accion not in acciones:
        raise TeleError("Acción no válida")
    cuerpo = f'<{acciones[accion]} xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">{argumentos}</{acciones[accion]}>'
    return ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f"<s:Body>{cuerpo}</s:Body></s:Envelope>")


async def dlna(control, accion, argumentos=""):
    async with httpx.AsyncClient(timeout=3) as c:
        r = await c.post(control, content=soap(control, accion, argumentos), headers={
            "Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"urn:schemas-upnp-org:service:AVTransport:1#{accion}"'})
        r.raise_for_status()
        return r.text


def registrar(uid, rol, accion, ok=True):
    with registro.origen("tele"):
        registro.anotar(uid, rol, "tele", accion, {}, ok, "", 0)
