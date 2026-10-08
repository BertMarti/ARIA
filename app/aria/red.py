"""Agente Redes: dispositivos de la LAN, inventario, latencia, test de velocidad e historial.

- Dispositivos: tabla de red de Pi-hole (`GET /api/network/devices`: hwaddr, interface, firstSeen,
  lastQuery, numQueries, macVendor, ips[{ip, name, lastSeen}]) combinada con el último escaneo de
  `aria-escaner` (que sí ve las MAC y el fabricante por ARP). Pi-hole corre en Docker y no ve las MAC
  de la LAN: sus «dispositivos» suelen llegar como `ip-192.168.0.x`.
- Inventario en `red_inventario` (data/aria.db): lo nuevo se marca como «no conocido» hasta que el
  administrador lo marque como conocido.
- Latencia: ICMP sin privilegios (socket de datagrama; Docker permite ping_group_range) y, si no se
  puede, tiempo de conexión TCP.
- Velocidad: descarga/subida cronometrada contra speed.cloudflare.com (sin binarios de terceros),
  ~20 MB en total y como mucho una vez cada 10 minutos.
"""
import asyncio
import ipaddress
import json
import socket
import sqlite3
import struct
import time
from contextlib import closing

import httpx

from . import config, db, escaneo, services, shield, vpn

DESTINOS = (("router", None), ("Cloudflare", "1.1.1.1"), ("Google", "8.8.8.8"))
BYTES_BAJADA = 15 * 1024 * 1024
TROZO_BAJADA = 5 * 1024 * 1024   # speed.cloudflare.com responde 403 a peticiones de más de ~10 MB
BYTES_SUBIDA = 5 * 1024 * 1024
INTERVALO_VELOCIDAD_S = 10 * 60
_lock_velocidad = asyncio.Lock()


class RedError(Exception):
    """Error legible (en español)."""


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS red_inventario (
                clave TEXT PRIMARY KEY, mac TEXT, ip TEXT, nombre TEXT, fabricante TEXT, alias TEXT,
                conocido INTEGER NOT NULL DEFAULT 0, primera_vez REAL NOT NULL, ultima_vez REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS red_mediciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, tipo TEXT NOT NULL, datos TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_red_med ON red_mediciones(tipo, ts);
        """)


def _en_lan(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(config.RED_PERMITIDA)
    except ValueError:
        return False


# --- Dispositivos ------------------------------------------------------------------------------------
def combinar(pihole: list, escaneo_hosts: list) -> list:
    """Une la tabla de Pi-hole y el último escaneo por IP (solo IPv4 de la red permitida)."""
    por_ip: dict = {}
    for d in pihole or []:
        hw = (d.get("hwaddr") or "").upper()
        mac = hw if hw and not hw.startswith("IP-") and hw != "00:00:00:00:00:00" else None
        for a in d.get("ips") or []:
            ip = a.get("ip") or ""
            if not _en_lan(ip):
                continue
            x = por_ip.setdefault(ip, {"ip": ip, "mac": None, "nombre": None, "fabricante": None,
                                       "ultima_consulta": None, "consultas": 0, "puertos": None})
            x["mac"] = x["mac"] or mac
            x["nombre"] = x["nombre"] or a.get("name") or None
            x["fabricante"] = x["fabricante"] or d.get("macVendor") or None
            vista = max(a.get("lastSeen") or 0, d.get("lastQuery") or 0)
            x["ultima_consulta"] = max(x["ultima_consulta"] or 0, vista) or None
            x["consultas"] += d.get("numQueries") or 0
    for h in escaneo_hosts or []:
        ip = h.get("ip") or ""
        if not _en_lan(ip):
            continue
        x = por_ip.setdefault(ip, {"ip": ip, "mac": None, "nombre": None, "fabricante": None,
                                   "ultima_consulta": None, "consultas": 0, "puertos": None})
        x["mac"] = h.get("mac") or x["mac"]
        x["fabricante"] = h.get("fabricante") or x["fabricante"]
        x["nombre"] = x["nombre"] or h.get("nombre")
        x["puertos"] = [p["puerto"] for p in h.get("puertos") or []]
    for x in por_ip.values():
        x["clave"] = x["mac"] or f"ip-{x['ip']}"
    return sorted(por_ip.values(), key=lambda x: tuple(int(p) for p in x["ip"].split(".")))


def _sincronizar(dispositivos: list) -> list:
    """Actualiza el inventario y devuelve los dispositivos con `conocido`, `alias` y `primera_vez`."""
    ahora = time.time()
    with closing(db._con()) as con, con:
        for d in dispositivos:
            # si ahora conocemos la MAC de una IP que estaba como ip-x, se hereda su estado
            previa = con.execute("SELECT * FROM red_inventario WHERE clave=?", (f"ip-{d['ip']}",)).fetchone()
            if d["mac"] and previa and not con.execute("SELECT 1 FROM red_inventario WHERE clave=?", (d["mac"],)).fetchone():
                con.execute("UPDATE red_inventario SET clave=?, mac=? WHERE clave=?", (d["mac"], d["mac"], f"ip-{d['ip']}"))
                for tabla in ("control_pausas", "control_servicios", "control_horarios"):  # control parental sigue al dispositivo
                    try:
                        con.execute(f"UPDATE OR REPLACE {tabla} SET clave=? WHERE clave=?", (d["mac"], f"ip-{d['ip']}"))
                    except sqlite3.OperationalError:
                        pass  # tabla aún sin crear
            con.execute("""INSERT INTO red_inventario (clave, mac, ip, nombre, fabricante, primera_vez, ultima_vez)
                           VALUES (?,?,?,?,?,?,?)
                           ON CONFLICT(clave) DO UPDATE SET ip=excluded.ip, ultima_vez=excluded.ultima_vez,
                             mac=COALESCE(excluded.mac, mac), nombre=COALESCE(excluded.nombre, nombre),
                             fabricante=COALESCE(excluded.fabricante, fabricante)""",
                        (d["clave"], d["mac"], d["ip"], d["nombre"], d["fabricante"], ahora, ahora))
            r = con.execute("SELECT conocido, alias, primera_vez FROM red_inventario WHERE clave=?", (d["clave"],)).fetchone()
            d.update({"conocido": bool(r["conocido"]), "alias": r["alias"], "primera_vez": r["primera_vez"]})
    return dispositivos


async def dispositivos() -> list:
    pihole = []
    if shield.configurado():
        try:
            pihole = (await shield._llamar("GET", "/api/network/devices",
                                           params={"max_devices": 200, "max_addresses": 10})).get("devices") or []
        except shield.ShieldError:
            pihole = []
    ult = await asyncio.to_thread(escaneo.ultimo)
    lista = combinar(pihole, (ult or {}).get("hosts") or [])
    return await asyncio.to_thread(_sincronizar, lista)


def marcar_conocido(clave: str, conocido: bool = True, alias: str | None = None) -> bool:
    with closing(db._con()) as con, con:
        if alias is not None:
            alias = " ".join(str(alias).split())[:40] or None
            return con.execute("UPDATE red_inventario SET conocido=?, alias=? WHERE clave=?",
                               (int(conocido), alias, clave)).rowcount > 0
        return con.execute("UPDATE red_inventario SET conocido=? WHERE clave=?", (int(conocido), clave)).rowcount > 0


def conocer_todos() -> int:
    with closing(db._con()) as con, con:
        return con.execute("UPDATE red_inventario SET conocido=1 WHERE conocido=0").rowcount


def buscar_clave(texto: str) -> str | None:
    """Encuentra un dispositivo del inventario por IP, alias, nombre o MAC."""
    t = str(texto or "").strip().lower()
    if not t:
        return None
    with closing(db._con()) as con:
        for r in con.execute("SELECT clave, ip, nombre, alias, mac FROM red_inventario"):
            if t in {(r["ip"] or "").lower(), (r["alias"] or "").lower(), (r["nombre"] or "").lower(),
                     (r["mac"] or "").lower(), r["clave"].lower()}:
                return r["clave"]
    return None


# --- Latencia -------------------------------------------------------------------------------------------
def _ping_icmp(ip: str, seq: int, timeout: float = 1.5) -> float | None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_ICMP) as s:
        s.settimeout(timeout)
        paquete = struct.pack("!BBHHH", 8, 0, 0, 0, seq) + b"aria-ping"  # el kernel pone id y checksum
        t0 = time.perf_counter()
        s.sendto(paquete, (ip, 0))
        while True:
            datos, _ = s.recvfrom(1024)
            if datos and datos[0] == 0:
                return (time.perf_counter() - t0) * 1000


def _ping_tcp(ip: str, timeout: float = 1.5) -> float | None:
    for puerto in (53, 443, 80):
        t0 = time.perf_counter()
        try:
            with socket.create_connection((ip, puerto), timeout=timeout):
                return (time.perf_counter() - t0) * 1000
        except ConnectionRefusedError:
            return (time.perf_counter() - t0) * 1000  # un RST también mide la ida y vuelta
        except OSError:
            continue
    return None


def _medir_destino(ip: str, n: int = 4) -> dict:
    tiempos, metodo = [], "icmp"
    for i in range(n):
        try:
            r = _ping_icmp(ip, i + 1)
        except PermissionError:
            metodo = "tcp"
            r = _ping_tcp(ip)
        except OSError:
            r = None
        if r is not None:
            tiempos.append(r)
    return {"ip": ip, "metodo": metodo, "enviados": n, "recibidos": len(tiempos),
            "perdida": round((n - len(tiempos)) * 100 / n),
            "media_ms": round(sum(tiempos) / len(tiempos), 1) if tiempos else None,
            "min_ms": round(min(tiempos), 1) if tiempos else None, "max_ms": round(max(tiempos), 1) if tiempos else None}


async def latencia(guardar: bool = True) -> dict:
    destinos = [(n, ip or config.ROUTER_IP) for n, ip in DESTINOS]
    res = await asyncio.gather(*(asyncio.to_thread(_medir_destino, ip) for _, ip in destinos))
    out = {"ts": time.time(), "destinos": [{"nombre": n, **r} for (n, _), r in zip(destinos, res)]}
    if guardar:
        await asyncio.to_thread(_guardar, "latencia", out)
    return out


# --- Velocidad -----------------------------------------------------------------------------------------
def _guardar(tipo: str, datos: dict) -> None:
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO red_mediciones (ts, tipo, datos) VALUES (?,?,?)", (datos["ts"], tipo, json.dumps(datos)))
        con.execute("DELETE FROM red_mediciones WHERE ts < ?", (time.time() - 90 * 86400,))


def ultima(tipo: str) -> dict | None:
    with closing(db._con()) as con:
        r = con.execute("SELECT datos FROM red_mediciones WHERE tipo=? ORDER BY ts DESC LIMIT 1", (tipo,)).fetchone()
    return json.loads(r["datos"]) if r else None


def historial(dias: int = 7) -> dict:
    desde = time.time() - max(1, min(int(dias), 90)) * 86400
    with closing(db._con()) as con:
        filas = con.execute("SELECT tipo, datos FROM red_mediciones WHERE ts >= ? ORDER BY ts", (desde,)).fetchall()
    out = {"latencia": [], "velocidad": []}
    for f in filas:
        d = json.loads(f["datos"])
        if f["tipo"] == "latencia":
            out["latencia"].append({"ts": d["ts"], **{x["nombre"]: x["media_ms"] for x in d["destinos"]}})
        elif f["tipo"] == "velocidad":
            out["velocidad"].append({k: d.get(k) for k in ("ts", "bajada_mbps", "subida_mbps", "latencia_ms")})
    return out


async def velocidad() -> dict:
    """Test de velocidad (Cloudflare). Como mucho uno cada 10 minutos (persistido en SQLite)."""
    if _lock_velocidad.locked():
        raise RedError("Ya hay un test de velocidad en marcha.")
    async with _lock_velocidad:
        prev = await asyncio.to_thread(ultima, "velocidad")
        if prev and time.time() - prev["ts"] < INTERVALO_VELOCIDAD_S:
            falta = int(INTERVALO_VELOCIDAD_S - (time.time() - prev["ts"])) // 60 + 1
            raise RedError(f"Solo se permite un test de velocidad cada 10 minutos (prueba dentro de {falta} min). "
                           f"Último: {prev['bajada_mbps']} Mbps de bajada y {prev['subida_mbps']} de subida.")
        base = config.SPEEDTEST_URL
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=5)) as c:
                # latencia HTTP (petición de 0 bytes)
                lat = []
                for _ in range(3):
                    t0 = time.perf_counter()
                    await c.get(f"{base}/__down", params={"bytes": 0})
                    lat.append((time.perf_counter() - t0) * 1000)
                t0, recibidos = time.perf_counter(), 0
                for _ in range(BYTES_BAJADA // TROZO_BAJADA):
                    async with c.stream("GET", f"{base}/__down", params={"bytes": TROZO_BAJADA}) as r:
                        if r.status_code != 200:
                            raise RedError(f"El servidor de pruebas devolvió {r.status_code}.")
                        async for trozo in r.aiter_bytes():
                            recibidos += len(trozo)
                t_baja = time.perf_counter() - t0
                datos = b"0" * BYTES_SUBIDA
                t0 = time.perf_counter()
                r = await c.post(f"{base}/__up", content=datos, headers={"Content-Type": "application/octet-stream"})
                t_sube = time.perf_counter() - t0
                if r.status_code >= 400:
                    raise RedError(f"El servidor de pruebas devolvió {r.status_code} en la subida.")
        except httpx.HTTPError:
            raise RedError("No se pudo contactar con el servidor de pruebas de velocidad.") from None
        out = {"ts": time.time(), "servidor": "speed.cloudflare.com",
               "bajada_mbps": round(recibidos * 8 / t_baja / 1e6, 1), "subida_mbps": round(len(datos) * 8 / t_sube / 1e6, 1),
               "latencia_ms": round(min(lat), 1), "bytes": recibidos + len(datos)}
        await asyncio.to_thread(_guardar, "velocidad", out)
        return out


# --- Salud (también para el rol usuario) -------------------------------------------------------------
async def salud() -> dict:
    lat = await asyncio.to_thread(ultima, "latencia")
    if not lat or time.time() - lat["ts"] > 600:
        lat = await latencia()
    srv = await services.estado()
    vpn_info = None
    if vpn.configurado():
        try:
            cl = await vpn.listar()
            vpn_info = {"dispositivos": len(cl), "conectados": sum(c["conectado"] for c in cl)}
        except vpn.VpnError:
            vpn_info = None
    return {"latencia": lat, "velocidad": await asyncio.to_thread(ultima, "velocidad"),
            "dns": srv["shield_dns"]["estado"], "vpn": srv["heimdall"]["estado"], "vpn_clientes": vpn_info}
