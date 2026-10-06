"""Comprobación del estado de SHIELD-DNS y HEIMDALL."""
import asyncio
import os
import socket
import struct

from . import config


def _tcp_ok(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _dns_ok(host: str, port: int, name: str = "example.com", timeout: float = 2.0) -> bool:
    """Consulta DNS (registro A) por UDP sin dependencias externas."""
    qid = struct.unpack(">H", os.urandom(2))[0]
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    query = header + qname + struct.pack(">HH", 1, 1)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            s.sendto(query, (host, port))
            data, _ = s.recvfrom(2048)
    except OSError:
        return False
    if len(data) < 12:
        return False
    rid, flags, _, ancount = struct.unpack(">HHHH", data[:8])
    return rid == qid and (flags & 0x000F) == 0 and ancount > 0


def _check_sync() -> dict:
    dns = _dns_ok(config.SHIELD_DNS_HOST, config.SHIELD_DNS_PORT)
    web = _tcp_ok(config.SHIELD_DNS_HOST, config.SHIELD_WEB_PORT)
    vpn = _tcp_ok(config.HEIMDALL_HOST, config.HEIMDALL_PORT)
    return {
        "shield_dns": {
            "nombre": "SHIELD-DNS",
            "dns_ok": dns,
            "web_ok": web,
            "estado": "ok" if dns and web else ("parcial" if dns or web else "no_instalado"),
            "puerto_web": config.SHIELD_WEB_PORT,
            "ruta_web": "/admin",
        },
        "heimdall": {
            "nombre": "HEIMDALL",
            "web_ok": vpn,
            "estado": "ok" if vpn else "no_instalado",
            "puerto_web": config.HEIMDALL_PORT,
            "ruta_web": "",
        },
    }


async def estado() -> dict:
    return await asyncio.to_thread(_check_sync)
