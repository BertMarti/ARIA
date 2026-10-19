"""Vídeo de las cámaras Tapo con go2rtc (contenedor `camaras`, solo en la red interna de ARIA).

go2rtc habla el protocolo propio de Tapo (puerto 8800, el de su app), así que vale también para las cámaras de
batería sin RTSP. Solo se conecta a una cámara mientras alguien la mira (no gasta batería ni red en reposo).
ARIA escribe su configuración (con la contraseña de Tapo, en un archivo que solo leen la app y go2rtc) y hace de
intermediario: el navegador nunca habla con go2rtc ni con las cámaras.
"""
import asyncio
import json
import logging
import os
from pathlib import Path
from urllib.parse import quote

import httpx

from . import config

log = logging.getLogger("aria.camaras")


def url_base() -> str:
    return os.environ.get("ARIA_CAMARAS_URL", "http://camaras:1984").rstrip("/")


def disponible() -> bool:
    return bool(config.TAPO_USUARIO and config.TAPO_PASSWORD and config.TAPO_CAMARAS)


def flujo(ip: str) -> str | None:
    """Nombre del flujo en go2rtc para una cámara de ARIA_TAPO_CAMARAS (c1, c2…); None si no es una de ellas."""
    try:
        return f"c{config.TAPO_CAMARAS.index(ip) + 1}"
    except ValueError:
        return None


def lan_ip_valida() -> bool:
    import ipaddress
    try:
        ip = ipaddress.ip_address(config.LAN_IP)
    except ValueError:
        return False
    return ip.is_private and not ip.is_loopback


def ruta_config() -> Path:
    return config.DATA_DIR / "camaras" / "go2rtc.yaml"


def escribir_config() -> bool:
    """Genera la configuración de go2rtc. Devuelve si ha cambiado (entonces hay que reiniciar el contenedor)."""
    ruta = ruta_config()
    # WebRTC solo para hablar por la cámara (el vídeo va por MSE a través de ARIA): el audio va del navegador a go2rtc
    # por el puerto 8555, publicado únicamente en la IP de casa (con la VPN también llega; desde Cloudflare, no).
    webrtc = ["webrtc:", '  listen: ""']
    if lan_ip_valida():
        # Sin STUN: no se consulta a servidores de fuera ni se anuncia la IP pública (solo se habla dentro de casa).
        webrtc = ["webrtc:", '  listen: ":8555"', "  candidates:", f"    - {config.LAN_IP}:8555", "  ice_servers: []"]
    lineas = ["# Generado por ARIA (hogar_camaras.py): no editar. Contiene la contraseña de Tapo.",
              "api:", '  listen: ":1984"', "rtsp:", '  listen: ""', *webrtc, "srtp:", '  listen: ""',
              "log:", "  level: warn", "streams:"]
    if disponible():
        clave = quote(config.TAPO_PASSWORD, safe="")
        lineas += [f"  {flujo(ip)}: tapo://{clave}@{ip}" for ip in config.TAPO_CAMARAS]
    texto = "\n".join(lineas) + "\n"
    try:
        if ruta.read_text(encoding="utf-8") == texto:
            return False
    except OSError:
        pass
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(".tmp")
    fd = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)   # la app y el grupo (go2rtc), nadie más
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(texto)
    os.replace(temporal, ruta)
    return True


_fotos: dict = {}   # ip -> (momento, jpeg): las miniaturas no despiertan a las cámaras de batería a cada rato
EDAD_MINIATURA = 10 * 60


async def foto(ip: str, max_edad: float = 0) -> bytes:
    """Una imagen de la cámara en JPEG (despierta a las de batería: puede tardar unos segundos). Con `max_edad`, vale
    una guardada si no es más vieja que eso."""
    import time
    nombre = flujo(ip)
    if not nombre:
        raise ValueError("Cámara no encontrada.")
    guardada = _fotos.get(ip)
    if max_edad and guardada and time.time() - guardada[0] < max_edad:
        return guardada[1]
    datos = await _foto_nueva(nombre)
    _fotos[ip] = (time.time(), datos)
    return datos


def edad_foto(ip: str) -> float | None:
    import time
    g = _fotos.get(ip)
    return time.time() - g[0] if g else None


async def _foto_nueva(nombre: str) -> bytes:
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.get(f"{url_base()}/api/frame.jpeg", params={"src": nombre})
    if r.status_code != 200 or not r.content.startswith(b"\xff\xd8"):
        raise RuntimeError("La cámara no ha enviado imagen.")
    return r.content


def _solo_video(texto: str) -> bool:
    """Para quien solo puede mirar: el único mensaje que sube es la petición del vídeo MSE (nada de WebRTC/hablar)."""
    try:
        m = json.loads(texto)
    except ValueError:
        return False
    return isinstance(m, dict) and m.get("type") == "mse" and set(m) <= {"type", "value"} and isinstance(m.get("value", ""), str)


async def reenviar(ws_navegador, ip: str, solo_ver: bool = False) -> None:
    """Vídeo en directo (MSE por WebSocket) de go2rtc al navegador y los mensajes de control en sentido contrario."""
    import websockets
    nombre = flujo(ip)
    destino = url_base().replace("http://", "ws://", 1) + "/api/ws?src=" + nombre
    try:
        async with websockets.connect(destino, max_size=8 * 1024 * 1024, open_timeout=10) as camara:
            async def subir():
                while True:
                    mensaje = await ws_navegador.receive()
                    if mensaje.get("type") == "websocket.disconnect":
                        return
                    if mensaje.get("text") is not None and len(mensaje["text"]) < 20000:   # control: codecs o SDP de WebRTC
                        if solo_ver and not _solo_video(mensaje["text"]):
                            continue
                        await camara.send(mensaje["text"])

            async def bajar():
                async for datos in camara:
                    if isinstance(datos, bytes):
                        await ws_navegador.send_bytes(datos)
                    else:
                        await ws_navegador.send_text(datos)
            tareas = [asyncio.create_task(subir()), asyncio.create_task(bajar())]
            _, pendientes = await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
            for t in pendientes:
                t.cancel()
    except Exception:  # noqa: BLE001 - sin cámara o sin go2rtc: se cierra sin traza (no se filtra nada)
        log.info("Directo de cámara terminado o no disponible")
    finally:
        try:
            await ws_navegador.close()
        except Exception:  # noqa: BLE001
            pass
