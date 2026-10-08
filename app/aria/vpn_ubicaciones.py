"""Aprendizaje de ubicaciones de conexiones de HEIMDALL.

Solo se envía la IP pública al servicio de geolocalización; la respuesta se conserva
como metadatos de ubicación, nunca como texto de la conexión.
"""
import ipaddress
import time
from contextlib import closing

import httpx

from . import config, db, vpn
from .avisos import Problema

GEO_URL = "https://ipwho.is/{}"
CACHE_S = 7 * 86400
TIMEOUT = 4
_transporte = None


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS vpn_ubicaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL,
                ip TEXT NOT NULL, pais TEXT NOT NULL DEFAULT '', ciudad TEXT NOT NULL DEFAULT '',
                operador TEXT NOT NULL DEFAULT '', primera_vez REAL NOT NULL, ultima_vez REAL NOT NULL,
                UNIQUE(cliente_id, ip));
            CREATE INDEX IF NOT EXISTS idx_vpn_ubicaciones_cliente ON vpn_ubicaciones(cliente_id, ultima_vez DESC);
            CREATE TABLE IF NOT EXISTS vpn_geo_cache (
                ip TEXT PRIMARY KEY, pais TEXT NOT NULL, ciudad TEXT NOT NULL, operador TEXT NOT NULL,
                guardado REAL NOT NULL);
        """)


def extraer_ip(endpoint: str | None) -> str | None:
    if not isinstance(endpoint, str):
        return None
    texto = endpoint.strip()
    if texto.startswith("[") and "]" in texto:
        texto = texto[1:texto.index("]")]
    elif texto.count(":") == 1:
        texto = texto.rsplit(":", 1)[0]
    try:
        ip = ipaddress.ip_address(texto)
    except ValueError:
        return None
    if not ip.is_global:
        return None
    try:
        if ip in ipaddress.ip_network(config.RED_PERMITIDA, strict=False):
            return None
    except ValueError:
        pass
    return str(ip)


async def _geolocalizar(ip: str) -> dict | None:
    ahora = time.time()
    with closing(db._con()) as con:
        fila = con.execute("SELECT pais, ciudad, operador FROM vpn_geo_cache WHERE ip=? AND guardado>?",
                           (ip, ahora - CACHE_S)).fetchone()
    if fila:
        return dict(fila)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, transport=_transporte) as cliente:
            r = await cliente.get(GEO_URL.format(ip))
        datos = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    if r.status_code >= 400 or not isinstance(datos, dict) or datos.get("success") is False:
        return None
    geo = {"pais": str(datos.get("country") or "Desconocido")[:80],
           "ciudad": str(datos.get("city") or "Desconocida")[:80],
           "operador": str((datos.get("connection") or {}).get("isp") or "Operador desconocido")[:120]}
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO vpn_geo_cache(ip,pais,ciudad,operador,guardado) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(ip) DO UPDATE SET pais=excluded.pais, ciudad=excluded.ciudad, "
                    "operador=excluded.operador, guardado=excluded.guardado", (ip, geo["pais"], geo["ciudad"], geo["operador"], ahora))
    return geo


def historial(cliente_id: int, limite: int = 10) -> list:
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute("SELECT ip, pais, ciudad, operador, primera_vez, ultima_vez "
                                              "FROM vpn_ubicaciones WHERE cliente_id=? ORDER BY ultima_vez DESC LIMIT ?",
                                              (cliente_id, limite))]


async def comprobar() -> list | None:
    if not vpn.configurado():
        return None
    try:
        clientes = await vpn.listar()
    except vpn.VpnError:
        return None
    problemas = []
    for cliente in clientes:
        if not cliente.get("conectado"):
            continue
        ip = extraer_ip(cliente.get("endpoint"))
        if not ip:
            continue
        geo = await _geolocalizar(ip)
        if not geo:
            continue
        ahora = time.time()
        with closing(db._con()) as con:
            vistas = con.execute("SELECT DISTINCT pais, operador FROM vpn_ubicaciones WHERE cliente_id=?", (cliente["id"],)).fetchall()
            primera = not vistas
            pais_nuevo = geo["pais"] not in {r["pais"] for r in vistas}
            operador_nuevo = geo["operador"] not in {r["operador"] for r in vistas}
            con.execute("INSERT INTO vpn_ubicaciones(cliente_id,ip,pais,ciudad,operador,primera_vez,ultima_vez) VALUES(?,?,?,?,?,?,?) "
                        "ON CONFLICT(cliente_id,ip) DO UPDATE SET ultima_vez=excluded.ultima_vez, pais=excluded.pais, ciudad=excluded.ciudad, operador=excluded.operador",
                        (cliente["id"], ip, geo["pais"], geo["ciudad"], geo["operador"], ahora, ahora))
        if not primera and (pais_nuevo or operador_nuevo):
            problemas.append(Problema(f"{cliente['id']}:{geo['pais']}:{geo['operador']}",
                                      f"🌍 VPN: «{cliente['nombre']}» se ha conectado desde un sitio nuevo: "
                                      f"{geo['ciudad']}, {geo['pais']} ({geo['operador']})"))
    return problemas
