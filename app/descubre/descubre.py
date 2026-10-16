"""Descubrimiento sin privilegios de Google Cast y renderizadores DLNA."""
import ipaddress
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlparse

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf


RED = ipaddress.ip_network(os.environ.get("ARIA_RED_PERMITIDA", "192.168.1.0/24"), strict=False)
SALIDA = Path("/descubre/dispositivos.json")
CAST = "_googlecast._tcp.local."
VISTO = {}
CAMBIO = threading.Event()
PARADA = threading.Event()


def error(exc):
    print(f"[descubre] {type(exc).__name__}", file=sys.stderr, flush=True)


def en_red(ip):
    try:
        return ipaddress.ip_address(ip).version == 4 and ipaddress.ip_address(ip) in RED
    except ValueError:
        return False


def txt(properties):
    resultado = {}
    for clave, valor in (properties or {}).items():
        try:
            k = clave.decode() if isinstance(clave, bytes) else str(clave)
            v = value = valor.decode(errors="replace") if isinstance(valor, bytes) else str(valor)
            resultado[k] = v
        except (AttributeError, UnicodeError):
            continue
    return resultado


def _bool_capacidad(valor):
    try:
        return bool(int(valor, 0) & 1)
    except (TypeError, ValueError):
        return False


def _cast(servicio, info):
    if not info:
        return None
    propiedades = txt(info.properties)
    ip = next((a for a in info.addresses if len(a) == 4), None)
    ip = socket.inet_ntoa(ip) if ip else ""
    if not en_red(ip):
        return None
    modelo = propiedades.get("md", "")[:200]
    nombre = propiedades.get("fn", servicio)[:200]
    identificador = propiedades.get("id", servicio.rstrip("."))
    grupo = "group" in modelo.lower() or "group" in nombre.lower()
    return {"id": f"cast:{identificador}", "nombre": nombre, "modelo": modelo,
            "tipo": "chromecast", "ip": ip, "puerto": info.port, "video": _bool_capacidad(propiedades.get("ca")),
            "grupo": grupo, "control": None}


class CastListener(ServiceListener):
    def add_service(self, zc, tipo, nombre):
        self.change(zc, tipo, nombre)

    def update_service(self, zc, tipo, nombre):
        self.change(zc, tipo, nombre)

    def remove_service(self, _zc, _tipo, nombre):
        for ident, dato in list(VISTO.items()):
            if dato.get("_servicio") == nombre:
                VISTO.pop(ident, None)
                CAMBIO.set()

    def change(self, zc, tipo, nombre):
        try:
            info = zc.get_service_info(tipo, nombre, timeout=1500)
            dato = _cast(nombre, info) if info else None
            if dato:
                dato["_servicio"] = nombre
                dato["_visto"] = time.time()
                VISTO[dato["id"]] = dato
                CAMBIO.set()
        except Exception as exc:
            error(exc)


def _url_segura(url, ip):
    try:
        dato = urlparse(url)
        return dato.scheme == "http" and dato.hostname == ip and 1 <= (dato.port or 80) <= 65535
    except (TypeError, ValueError):
        return False


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _xml(url, ip):
    if not _url_segura(url, ip):
        return None
    peticion = urllib.request.Request(url, headers={"User-Agent": "ARIA-descubre"})
    abridor = urllib.request.build_opener(_SinRedirecciones)
    with abridor.open(peticion, timeout=2) as respuesta:
        datos = respuesta.read(256 * 1024 + 1)
    if len(datos) > 256 * 1024 or re.search(br"<!DOCTYPE", datos, re.I):
        return None
    return ET.fromstring(datos)


def _dlna(respuesta, ip_respuesta=None):
    cabeceras = {}
    for linea in respuesta.decode(errors="ignore").splitlines()[1:]:
        if ":" in linea:
            clave, valor = linea.split(":", 1)
            cabeceras[clave.lower()] = valor.strip()
    location = cabeceras.get("location")
    try:
        ip = urlparse(location).hostname
        if not ip or not en_red(ip) or (ip_respuesta and ip != ip_respuesta):
            return None
        raiz = _xml(location, ip)
        if raiz is None:
            return None
        textos = {x.tag.rsplit("}", 1)[-1]: (x.text or "").strip() for x in raiz.iter()}
        control = None
        for servicio in raiz.iter():
            if not servicio.tag.endswith("service"):
                continue
            valores = {x.tag.rsplit("}", 1)[-1]: (x.text or "").strip() for x in servicio}
            if "AVTransport" in valores.get("serviceType", ""):
                candidato = urljoin(location, valores.get("controlURL", ""))
                if _url_segura(candidato, ip):
                    control = candidato
                break
        udn = textos.get("UDN", location)
        return {"id": f"dlna:{udn}", "nombre": textos.get("friendlyName", ip),
                "modelo": textos.get("modelName", ""), "tipo": "dlna", "ip": ip,
                "puerto": urlparse(location).port or 80, "video": True, "grupo": False, "control": control}
    except (OSError, ValueError, ET.ParseError, urllib.error.URLError):
        return None


def sondear_dlna():
    mensaje = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
               "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\nMX: 2\r\n\r\n").encode()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
            sock.settimeout(3)
            sock.sendto(mensaje, ("239.255.255.250", 1900))
            while True:
                try:
                    datos, origen = sock.recvfrom(4096)
                except socket.timeout:
                    break
                if en_red(origen[0]):
                    dato = _dlna(datos, origen[0])
                    if dato:
                        dato["_visto"] = time.time()
                        VISTO[dato["id"]] = dato
                        CAMBIO.set()
    except OSError as exc:
        error(exc)


def escribir():
    ahora = time.time()
    for ident, dato in list(VISTO.items()):
        if ahora - dato.get("_visto", 0) > 300:
            VISTO.pop(ident, None)
    salida = []
    for dato in VISTO.values():
        salida.append({k: dato.get(k) for k in ("id", "nombre", "modelo", "tipo", "ip", "puerto", "video", "grupo", "control")})
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix="dispositivos.", dir=SALIDA.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as archivo:
            json.dump({"ts": ahora, "dispositivos": salida}, archivo, ensure_ascii=True)
            archivo.flush()
            os.fchmod(archivo.fileno(), 0o640)
        os.replace(temporal, SALIDA)
    except Exception as exc:
        error(exc)
        try:
            os.unlink(temporal)
        except OSError:
            pass


def main():
    try:
        zc = Zeroconf()
        ServiceBrowser(zc, CAST, CastListener())
    except Exception as exc:
        error(exc)
        zc = None
    proximo_ssdp = 0
    while not PARADA.is_set():
        if time.time() >= proximo_ssdp:
            sondear_dlna()
            proximo_ssdp = time.time() + 60
        escribir()
        CAMBIO.wait(10)
        CAMBIO.clear()
    if zc:
        zc.close()


if __name__ == "__main__":
    main()
