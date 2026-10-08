"""Seguridad y Redes: guardia de CIDR, parser de nmap, CVE con OSV falso, hallazgos y permisos."""
import asyncio
import json
import time

import pytest

from aria import config, cve, escaneo, red, seguridad, usuarios
from aria.escaneo_comun import ObjetivoNoPermitido, parsear_nmap_xml, red_permitida, validar_objetivos
from tests.test_permisos import cliente_de


@pytest.mark.parametrize("malo", ["8.8.8.8", "10.0.0.0/8", "192.168.1.0/24", "192.168.0.0/16", "router.local",
                                  "localhost", "example.com", "192.168.0.1-50", "-sV", "192.168.0.1 8.8.8.8",
                                  "::1", "fe80::1", "192.168.0.300", "192.168.0.0/24;rm -rf /", ""])
def test_cidr_guard_rechaza(malo):
    with pytest.raises(ObjetivoNoPermitido):
        validar_objetivos([malo], "192.168.0.0/24")


def test_cidr_guard_acepta():
    assert validar_objetivos(["192.168.0.0/24", "192.168.0.10", "192.168.0.128/25"], "192.168.0.0/24") == \
        ["192.168.0.0/24", "192.168.0.10", "192.168.0.128/25"]
    with pytest.raises(ObjetivoNoPermitido):
        validar_objetivos([], "192.168.0.0/24")
    for mala in ("8.8.8.0/24", "0.0.0.0/0", "10.0.0.0/8", "nada"):
        with pytest.raises(ObjetivoNoPermitido):
            red_permitida(mala)


def test_solicitar_escaneo_valida_y_limita(tmp_path, monkeypatch):
    (tmp_path / "escaner").mkdir()
    with pytest.raises(escaneo.EscaneoError, match="fuera de la red"):
        escaneo.solicitar("rapido", ["8.8.8.8"])
    with pytest.raises(escaneo.EscaneoError):
        escaneo.solicitar("agresivo")
    pid = escaneo.solicitar("rapido")
    pet = json.loads((tmp_path / "escaner" / "peticiones" / f"{pid}.json").read_text())
    assert pet["objetivos"] == ["192.168.0.0/24"] and pet["perfil"] == "rapido"
    (tmp_path / "escaner" / "peticiones" / f"{pid}.json").unlink()
    with pytest.raises(escaneo.EscaneoError, match="10 minutos"):
        escaneo.solicitar("rapido")


NMAP_XML = """<?xml version="1.0"?><!DOCTYPE nmaprun><nmaprun scanner="nmap" start="1791360000">
<host><status state="up"/><address addr="192.168.0.1" addrtype="ipv4"/>
<address addr="aa:bb:cc:00:00:01" addrtype="mac" vendor="TP-Link"/>
<hostnames><hostname name="router.lan" type="PTR"/></hostnames><ports>
<port protocol="tcp" portid="80"><state state="open"/><service name="http" product="TP-LINK router http config"><cpe>cpe:/h:tp-link:router</cpe></service></port>
<port protocol="tcp" portid="23"><state state="open"/><service name="telnet"/></port>
<port protocol="tcp" portid="443"><state state="closed"/><service name="https"/></port>
</ports></host>
<host><status state="up"/><address addr="192.168.0.50" addrtype="ipv4"/><ports>
<port protocol="tcp" portid="22"><state state="open"/><service name="ssh" product="OpenSSH" version="9.2p1 Debian 2+deb12u3"><cpe>cpe:/a:openbsd:openssh:9.2p1</cpe></service></port>
<port protocol="tcp" portid="445"><state state="open"/><service name="microsoft-ds"/></port>
</ports></host>
<host><status state="down"/><address addr="192.168.0.99" addrtype="ipv4"/></host>
<runstats><finished time="1791360100" summary="256 IP addresses (2 hosts up)"/></runstats></nmaprun>"""


def test_parser_nmap():
    r = parsear_nmap_xml(NMAP_XML)
    assert [h["ip"] for h in r["hosts"]] == ["192.168.0.1", "192.168.0.50"]
    router = r["hosts"][0]
    assert router["fabricante"] == "TP-Link" and router["nombre"] == "router.lan"
    assert [p["puerto"] for p in router["puertos"]] == [23, 80]  # el cerrado no aparece
    ssh = r["hosts"][1]["puertos"][0]
    assert ssh["producto"] == "OpenSSH" and ssh["cpe"] == ["cpe:/a:openbsd:openssh:9.2p1"]
    assert r["fin"] == 1791360100
    with pytest.raises(ValueError):
        parsear_nmap_xml('<!DOCTYPE x [<!ENTITY a "b">]><nmaprun/>')


FAKE_OSV = {"vulns": [
    {"id": "DEBIAN-CVE-2023-38408", "aliases": ["CVE-2023-38408"], "summary": "ssh-agent remote code execution",
     "severity": [{"type": "CVSS_V3", "score": "9.8"}]},
    {"id": "DEBIAN-CVE-2007-2768", "summary": "viejo y menor"},
]}


def test_cve_con_osv_falso(monkeypatch):
    llamadas = []

    async def post(cuerpo):
        llamadas.append(cuerpo)
        return FAKE_OSV
    monkeypatch.setattr(cve, "_post_osv", post)
    srv = parsear_nmap_xml(NMAP_XML)["hosts"][1]["puertos"][0]
    q = cve.consulta_para(srv)
    assert q["fuente"] == "osv" and q["ecosistema"] == "Debian:12" and q["version"] == "1:9.2p1-2+deb12u3"
    r = asyncio.run(cve.buscar(srv))
    assert [v["id"] for v in r["vulns"]] == ["CVE-2023-38408", "DEBIAN-CVE-2007-2768"]
    assert r["vulns"][0]["gravedad"] == "alta" and r["vulns"][1]["gravedad"] == "baja"
    assert llamadas == [{"package": {"name": "openssh", "ecosystem": "Debian:12"}, "version": "1:9.2p1-2+deb12u3"}]
    r2 = asyncio.run(cve.buscar(srv))  # segunda vez: caché, sin red
    assert r2["cache"] and len(llamadas) == 1
    assert cve.consulta_para({"producto": "nginx", "version": None}) is None
    q = cve.consulta_para({"producto": "nginx", "version": "1.18.0", "cpe": ["cpe:/a:igor_sysoev:nginx:1.18.0"]})
    assert q == {"fuente": "nvd", "cpe": "cpe:2.3:a:igor_sysoev:nginx:1.18.0", "clave": "nvd|cpe:2.3:a:igor_sysoev:nginx:1.18.0"}


def test_hallazgos(monkeypatch):
    monkeypatch.setattr(config, "ROUTER_IP", "192.168.0.1")
    monkeypatch.setattr(config, "LAN_IP", "192.168.1.50")
    res = parsear_nmap_xml(NMAP_XML)
    res["udp_router"] = [{"puerto": 1900, "estado": "open"}]
    anterior = {"hosts": [{"ip": "192.168.0.50", "puertos": [{"proto": "tcp", "puerto": 22}]}]}
    h = seguridad.hallazgos_de_escaneo(res, anterior, {})
    tipos = {(x["tipo"], x["gravedad"], x["ip"]) for x in h}
    assert ("servicio_riesgo", "alta", "192.168.0.1") in tipos          # telnet
    assert ("panel_admin", "media", "192.168.0.1") in tipos             # web del router sin TLS
    assert ("servicio_riesgo", "media", "192.168.0.50") in tipos        # SMB
    assert ("puerto_nuevo", "media", "192.168.0.50") in tipos           # 445 no estaba antes
    assert ("router", "media", "192.168.0.1") in tipos                  # UPnP
    vpn = seguridad.hallazgos_de_vpn([{"nombre": "viejo", "activo": True, "ultimo_handshake": None},
                                      {"nombre": "usado", "activo": True, "ultimo_handshake": "2026-10-01T00:00:00Z"},
                                      {"nombre": "apagado", "activo": False, "ultimo_handshake": None}])
    assert [x["titulo"] for x in vpn] == ["Peer de WireGuard activo y nunca usado: viejo"]
    inv = seguridad.hallazgos_de_inventario([{"ip": "192.168.0.77", "conocido": False, "primera_vez": time.time()},
                                             {"ip": "192.168.0.5", "conocido": True}])
    assert len(inv) == 1 and inv[0]["gravedad"] == "media" and "1 dispositivo" in inv[0]["titulo"]
    assert seguridad.hallazgos_de_inventario([{"ip": "192.168.0.5", "conocido": True}]) == []


def test_inventario_combina_pihole_y_escaneo():
    pihole = [{"hwaddr": "ip-192.168.0.50", "macVendor": "", "lastQuery": 100, "numQueries": 7,
               "ips": [{"ip": "192.168.0.50", "name": "portatil.lan", "lastSeen": 90}]},
              {"hwaddr": "ip-10.8.0.2", "ips": [{"ip": "10.8.0.2", "name": "movil-vpn"}]},
              {"hwaddr": "00:00:00:00:00:00", "ips": [{"ip": "127.0.0.1", "name": "localhost"}]}]
    hosts = parsear_nmap_xml(NMAP_XML)["hosts"]
    ds = red.combinar(pihole, hosts)
    assert [d["ip"] for d in ds] == ["192.168.0.1", "192.168.0.50"]
    assert ds[0]["clave"] == "AA:BB:CC:00:00:01" and ds[1]["clave"] == "ip-192.168.0.50"
    assert ds[1]["nombre"] == "portatil.lan" and ds[1]["puertos"] == [22, 445]
    ds = red._sincronizar(ds)
    assert not any(d["conocido"] for d in ds)
    assert red.marcar_conocido("AA:BB:CC:00:00:01", True, "Router")
    assert red.buscar_clave("Router") == "AA:BB:CC:00:00:01" and red.buscar_clave("192.168.0.50") == "ip-192.168.0.50"
    assert red._sincronizar(red.combinar(pihole, hosts))[0]["conocido"]


def test_velocidad_limitada(monkeypatch):
    red._guardar("velocidad", {"ts": time.time(), "bajada_mbps": 500, "subida_mbps": 100, "latencia_ms": 5})
    with pytest.raises(red.RedError, match="10 minutos"):
        asyncio.run(red.velocidad())


# --- Permisos de los endpoints nuevos ---
ADMIN_NUEVOS = [
    ("GET", "/api/red/dispositivos"), ("POST", "/api/red/dispositivos/conocido"),
    ("POST", "/api/red/dispositivos/conocer-todos"), ("POST", "/api/red/latencia"), ("POST", "/api/red/velocidad"),
    ("GET", "/api/red/historial"), ("GET", "/api/seguridad/informe"), ("GET", "/api/seguridad/escaneo"),
    ("POST", "/api/seguridad/escaneo"),
]


@pytest.mark.parametrize("metodo,ruta", ADMIN_NUEVOS)
def test_usuario_403_en_red_y_seguridad(metodo, ruta):
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    assert cliente_de(ana).request(metodo, ruta, json={}).status_code == 403


def test_matriz_finanzas_y_salud(monkeypatch):
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")

    async def salud():
        return {"latencia": None}
    monkeypatch.setattr(red, "salud", salud)
    c = cliente_de(ana)
    for ruta in ("/api/finanzas/resumen", "/api/finanzas/movimientos", "/api/finanzas/reglas", "/api/red/salud",
                 "/api/agentes"):
        assert c.get(ruta).status_code == 200, ruta
    admin = usuarios.por_identificador("admin")
    assert cliente_de(admin).get("/api/seguridad/escaneo").status_code == 200
    r = cliente_de(admin).post("/api/seguridad/escaneo", json={"objetivos": ["8.8.8.8"]})
    assert r.status_code == 400 and "fuera de la red" in r.json()["error"]


# --- Dispositivos que cambian de IP (vecinos ARP de aria-escaner) ---
def _ph(ip, ultima):
    return {"hwaddr": f"ip-{ip}", "lastQuery": ultima, "numQueries": 3, "ips": [{"ip": ip, "lastSeen": ultima}]}


def test_vecinos_mandan_sobre_el_escaneo_viejo():
    hosts = [{"ip": "192.168.0.60", "mac": "62:00:00:00:00:01", "fabricante": None, "puertos": []}]
    ds = red.combinar([_ph("192.168.0.60", 100), _ph("192.168.0.58", 200)], hosts, {"192.168.0.58": "62:00:00:00:00:01"})
    por_ip = {d["ip"]: d["clave"] for d in ds}
    assert por_ip == {"192.168.0.58": "62:00:00:00:00:01", "192.168.0.60": "ip-192.168.0.60"}


def test_dispositivo_conocido_que_cambia_de_ip_no_sale_como_nuevo(monkeypatch):
    mac = "62:00:00:00:00:01"
    hosts = [{"ip": "192.168.0.60", "mac": mac, "fabricante": None, "puertos": []}]
    red._sincronizar(red.combinar([_ph("192.168.0.60", 100)], hosts))
    assert red.marcar_conocido(mac, True, "Móvil de Ana")
    # Cambia a .58: Pi-hole aún lo ve como ip-.58 (y la .60 vieja sigue en su tabla) hasta que llegan los vecinos
    antes = red._sincronizar(red.combinar([_ph("192.168.0.60", 100), _ph("192.168.0.58", 150)], hosts))
    assert {d["ip"]: d["conocido"] for d in antes} == {"192.168.0.58": False, "192.168.0.60": True}
    t0 = time.time()
    monkeypatch.setattr(red.time, "time", lambda: t0)
    ds = red._sincronizar(red.combinar([_ph("192.168.0.60", 100), _ph("192.168.0.58", 150)], hosts,
                                       {"192.168.0.58": mac}))
    assert [(d["ip"], d["clave"], d["conocido"], d["alias"]) for d in ds] == [("192.168.0.58", mac, True, "Móvil de Ana")]
    from contextlib import closing
    with closing(red.db._con()) as con:
        claves = {r[0] for r in con.execute("SELECT clave FROM red_inventario")}
    assert claves == {mac}  # ni ip-.58 ni ip-.60 quedan como «desconocidos»
    # Si más tarde otro aparato usa la .60 (actividad posterior al cambio), sí aparece como nuevo
    ds = red._sincronizar(red.combinar([_ph("192.168.0.60", t0 + 3600), _ph("192.168.0.58", 150)], hosts,
                                       {"192.168.0.58": mac}))
    assert {d["ip"]: d["conocido"] for d in ds} == {"192.168.0.58": True, "192.168.0.60": False}


def test_fusion_conserva_alias_de_la_fila_por_ip():
    mac = "62:00:00:00:00:02"
    red._sincronizar(red.combinar([_ph("192.168.0.70", 100)], []))
    assert red.marcar_conocido("ip-192.168.0.70", True, "Tele")
    red._sincronizar(red.combinar([], [{"ip": "192.168.0.71", "mac": mac, "fabricante": None, "puertos": []}]))
    ds = red._sincronizar(red.combinar([_ph("192.168.0.70", 100)], [], {"192.168.0.70": mac}))
    assert [(d["clave"], d["alias"], d["conocido"]) for d in ds] == [(mac, "Tele", True)]


def test_vecinos_viejos_se_ignoran(tmp_path, monkeypatch):
    from aria import escaneo
    monkeypatch.setattr(config, "ESCANER_DIR", tmp_path)
    (tmp_path / "vecinos.json").write_text(json.dumps({"ts": time.time() - 3600, "vecinos": {"192.168.0.5": "aa:bb:cc:dd:ee:ff"}}))
    assert escaneo.vecinos() == {}
    (tmp_path / "vecinos.json").write_text(json.dumps({"ts": time.time(), "vecinos": {"192.168.0.5": "aa:bb:cc:dd:ee:ff"}}))
    assert escaneo.vecinos() == {"192.168.0.5": "AA:BB:CC:DD:EE:FF"}
