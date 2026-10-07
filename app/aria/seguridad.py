"""Agente Seguridad (Intel): informe DEFENSIVO de la red de casa, solo para administradores.

Solo lee: resultados del escáner (nmap en `aria-escaner`, limitado a la red permitida), inventario de
dispositivos, Pi-hole y wg-easy. Nunca ataca, explota ni prueba contraseñas. La exposición externa de la
IP pública no se comprueba (ver README): haría falta un servicio de terceros que escanee desde fuera.
"""
import asyncio
import re
import time
from collections import Counter

from . import config, cve, escaneo, red, shield, vpn

ORDEN = {"alta": 0, "media": 1, "baja": 2, "info": 3}

# puerto TCP -> (gravedad, título, recomendación)
RIESGOS = {
    23: ("alta", "Telnet abierto", "Telnet envía todo sin cifrar: desactívalo en el dispositivo y usa SSH."),
    2323: ("alta", "Telnet alternativo abierto", "Puerto típico de cámaras/IoT vulnerables: desactívalo o aísla el dispositivo."),
    3389: ("alta", "Escritorio remoto (RDP) abierto", "Desactiva RDP si no lo usas o limita quién puede conectarse."),
    5900: ("alta", "VNC abierto", "VNC suele ir sin cifrar: desactívalo o protégelo con contraseña fuerte y solo en la LAN."),
    2375: ("alta", "API de Docker sin TLS", "Quien llegue a este puerto controla los contenedores: ciérralo."),
    21: ("media", "FTP abierto", "FTP no cifra las contraseñas: usa SFTP o desactívalo."),
    445: ("media", "SMB (compartición de Windows) abierto", "Comparte solo lo necesario, desactiva SMBv1 y usa contraseñas."),
    139: ("media", "NetBIOS abierto", "Servicio antiguo de Windows: desactívalo si no hace falta."),
    1900: ("media", "UPnP (SSDP) abierto", "UPnP permite abrir puertos del router sin pedir permiso: desactívalo en el router."),
    5000: ("media", "UPnP/servicio en 5000 abierto", "En routers suele ser UPnP; si no lo usas, desactívalo."),
    5431: ("media", "UPnP (5431) abierto", "Desactiva UPnP en el router si no lo necesitas."),
    3306: ("media", "Base de datos MySQL accesible", "Las bases de datos no deberían escuchar en toda la LAN."),
    5432: ("media", "Base de datos PostgreSQL accesible", "Limita la escucha a localhost o a la red de Docker."),
    6379: ("media", "Redis accesible", "Redis sin contraseña permite leer y escribir datos: limita su escucha."),
    27017: ("media", "MongoDB accesible", "Limita la escucha y activa la autenticación."),
    9200: ("media", "Elasticsearch accesible", "Limita la escucha y activa la autenticación."),
    8291: ("media", "Winbox (MikroTik) abierto", "Panel de administración de router: limítalo."),
}
_PANEL = re.compile(r"admin|router|config|management|panel|tp-?link|webui|login", re.I)
_RASTREADOR = re.compile(r"analytic|track|telemetr|metric|stat|pixel|beacon|adservice|doubleclick|ads?\.|adsystem|"
                         r"crashlytics|app-measurement|sentry|segment|mixpanel|appsflyer|branch\.io|hotjar", re.I)
_MALWARE = re.compile(r"malware|phish|botnet|coinhive|cryptominer|\.xyz$|\.top$|\.tk$", re.I)


def _h(gravedad, tipo, titulo, detalle, recomendacion="", ip=None) -> dict:
    return {"gravedad": gravedad, "tipo": tipo, "titulo": titulo, "detalle": detalle,
            "recomendacion": recomendacion, "ip": ip}


def _nombre(ip: str, inventario: dict) -> str:
    d = inventario.get(ip) or {}
    n = d.get("alias") or d.get("nombre") or d.get("fabricante")
    return f"{n} ({ip})" if n else ip


def hallazgos_de_escaneo(res: dict, anterior: dict | None, inventario: dict) -> list:
    """Puertos de riesgo, paneles web, puertos nuevos respecto al escaneo anterior y UPnP del router."""
    out = []
    previos = {h["ip"]: {(p["proto"], p["puerto"]) for p in h.get("puertos") or []}
               for h in (anterior or {}).get("hosts") or []}
    for h in res.get("hosts") or []:
        ip = h["ip"]
        quien = _nombre(ip, inventario)
        es_pi = ip == config.LAN_IP
        es_router = ip == config.ROUTER_IP
        for p in h.get("puertos") or []:
            n, servicio = p["puerto"], (p.get("servicio") or "")
            desc = " ".join(x for x in (p.get("producto"), p.get("version")) if x) or servicio or "desconocido"
            if p.get("proto") == "tcp" and n in RIESGOS:
                g, t, rec = RIESGOS[n]
                out.append(_h(g, "servicio_riesgo", f"{t} en {quien}", f"Puerto {n}/tcp: {desc}.", rec, ip))
            elif p.get("proto") == "tcp" and servicio.startswith("http") and not es_pi:
                tls = "ssl" in servicio or "https" in servicio or n in (443, 8443)
                texto = f"{p.get('producto') or ''} {p.get('extra') or ''}"
                if es_router or _PANEL.search(texto):
                    g = "media" if not tls else "baja"
                    out.append(_h(g, "panel_admin", f"Panel de administración web en {quien}",
                                  f"Puerto {n}/tcp ({'HTTPS' if tls else 'HTTP sin cifrar'}): {desc}.",
                                  "Cambia la contraseña por defecto, desactiva la gestión remota (desde Internet) "
                                  "y usa HTTPS si el dispositivo lo permite.", ip))
            if anterior is not None and ip in previos and (p["proto"], n) not in previos[ip]:
                out.append(_h("media", "puerto_nuevo", f"Puerto nuevo abierto en {quien}",
                              f"{n}/{p['proto']} ({desc}) no estaba abierto en el escaneo anterior.",
                              "Comprueba si has instalado o activado algo; si no lo reconoces, investígalo.", ip))
    for u in res.get("udp_router") or []:
        if u.get("estado") == "open":
            nombre = {1900: "UPnP (SSDP)", 5351: "NAT-PMP/PCP"}.get(u.get("puerto"), f"UDP {u.get('puerto')}")
            out.append(_h("media", "router", f"{nombre} activo en el router",
                          f"El router responde en {u.get('puerto')}/udp.",
                          "Cualquier dispositivo de casa puede abrir puertos hacia Internet sin avisar. Desactívalo "
                          "en el router (TP-Link: Avanzado → NAT → UPnP) salvo que una consola o app lo necesite.",
                          config.ROUTER_IP))
    return out


def hallazgos_de_inventario(dispositivos: list) -> list:
    out = []
    for d in dispositivos:
        if not d.get("conocido"):
            quien = d.get("alias") or d.get("nombre") or d.get("fabricante") or "sin nombre"
            out.append(_h("media" if time.time() - (d.get("primera_vez") or 0) < 7 * 86400 else "baja",
                          "dispositivo_desconocido", f"Dispositivo no reconocido: {quien} ({d['ip']})",
                          "Está en la red y no se ha marcado como conocido.",
                          "Si es tuyo, márcalo como conocido en Red; si no, cambia la contraseña del WiFi.", d["ip"]))
    return out


def hallazgos_de_vpn(clientes: list) -> list:
    return [_h("baja", "vpn_sin_uso", f"Peer de WireGuard activo y nunca usado: {c['nombre']}",
               "Está activado pero nunca se ha conectado.",
               "Si ya no lo necesitas, desactívalo o bórralo en HEIMDALL; cada peer es una llave de entrada.")
            for c in clientes if c.get("activo") and not c.get("ultimo_handshake")]


async def hallazgos_de_cves(res: dict, inventario: dict, max_nuevas: int = 8) -> list:
    out, nuevas = [], 0
    for h in res.get("hosts") or []:
        for p in h.get("puertos") or []:
            q = cve.consulta_para(p)
            if not q:
                continue
            r = await cve.buscar(p, permitir_red=nuevas < max_nuevas)
            if r and not r.get("cache"):
                nuevas += 1
            if not r or not r["vulns"]:
                continue
            vs = r["vulns"]
            peor = min(vs, key=lambda v: ORDEN[v["gravedad"]])
            ids = ", ".join(v["id"] for v in vs[:5])
            desc = " ".join(x for x in (p.get("producto"), p.get("version")) if x)
            out.append(_h(peor["gravedad"], "cve", f"{desc} con vulnerabilidades conocidas en {_nombre(h['ip'], inventario)}",
                          f"{len(vs)} aviso(s) en {r['fuente'].upper()} para el puerto {p['puerto']}: {ids}"
                          f"{'…' if len(vs) > 5 else ''}.",
                          "Actualiza el firmware o el paquete. Los avisos de Debian sin puntuación suelen estar "
                          "mitigados o ser menores; revisa los de gravedad alta.", h["ip"]))
    return out


async def bloqueos_por_cliente(clientes: int = 5, dominios: int = 5) -> list:
    """Dominios más bloqueados por Pi-hole para los clientes con más bloqueos (últimas 24 h)."""
    if not shield.configurado():
        return []
    top = await shield._llamar("GET", "/api/stats/top_clients", params={"blocked": "true", "count": clientes})
    out = []
    for c in top.get("clients") or []:
        q = await shield._llamar("GET", "/api/queries", params={"client_ip": c.get("ip"), "upstream": "blocklist",
                                                                 "length": 1000})
        cuenta = Counter(x.get("domain") for x in q.get("queries") or [] if x.get("domain"))
        out.append({"cliente": c.get("name") or c.get("ip"), "ip": c.get("ip"), "bloqueadas": c.get("count", 0),
                    "dominios": [{"dominio": d, "veces": n,
                                  "tipo": "malware?" if _MALWARE.search(d) else "rastreador" if _RASTREADOR.search(d) else "publicidad/otros"}
                                 for d, n in cuenta.most_common(dominios)]})
    return out


async def informe(con_cves: bool = True) -> dict:
    res = await asyncio.to_thread(escaneo.ultimo)
    disp = await red.dispositivos()
    inventario = {d["ip"]: d for d in disp}
    hall: list = []
    if not res:
        hall.append(_h("info", "sin_escaneo", "Aún no hay ningún escaneo",
                       "Lanza un escaneo en Seguridad o espera al escaneo semanal programado.", ""))
    elif res.get("error"):
        hall.append(_h("info", "escaneo_fallido", "El último escaneo falló", str(res["error"])[:200], ""))
    else:
        hall += hallazgos_de_escaneo(res, await asyncio.to_thread(escaneo.anterior_a, res.get("id")), inventario)
        if con_cves:
            hall += await hallazgos_de_cves(res, inventario)
    hall += hallazgos_de_inventario(disp)
    clientes_vpn = []
    if vpn.configurado():
        try:
            clientes_vpn = await vpn.listar()
        except vpn.VpnError:
            hall.append(_h("info", "vpn", "No se pudo consultar HEIMDALL", "", ""))
    hall += hallazgos_de_vpn(clientes_vpn)
    try:
        bloqueos = await bloqueos_por_cliente()
    except shield.ShieldError:
        bloqueos = []
    hall.append(_h("info", "exposicion_externa", "Exposición desde Internet no comprobada",
                   "ARIA no escanea tu IP pública: necesitaría un servicio externo que la escanee desde fuera.",
                   "Revisa en el router que no haya redirecciones de puertos aparte de UDP 51820 (VPN) y que la "
                   "gestión remota esté desactivada.", None))
    hall.sort(key=lambda x: (ORDEN[x["gravedad"]], x["tipo"], x["ip"] or ""))
    cuenta = Counter(h["gravedad"] for h in hall)
    return {"generado": time.time(), "red": config.RED_PERMITIDA,
            "escaneo": {k: res.get(k) for k in ("id", "perfil", "origen", "inicio", "fin")} | {
                "hosts": len(res.get("hosts") or []),
                "puertos_abiertos": sum(len(h.get("puertos") or []) for h in res.get("hosts") or [])} if res else None,
            "resumen": {g: cuenta.get(g, 0) for g in ("alta", "media", "baja", "info")},
            "hallazgos": hall, "bloqueos": bloqueos, "dispositivos": len(disp),
            "desconocidos": sum(1 for d in disp if not d.get("conocido")),
            "estado_escaner": await asyncio.to_thread(escaneo.estado)}


def texto_informe(inf: dict, maximo: int = 12) -> str:
    """Resumen en texto para el modelo (sin MAC)."""
    r = inf["resumen"]
    e = inf.get("escaneo")
    cab = (f"Informe de seguridad de {inf['red']}: {r['alta']} alta(s), {r['media']} media(s), {r['baja']} baja(s). "
           f"Dispositivos: {inf['dispositivos']} ({inf['desconocidos']} sin reconocer). ")
    if e:
        cab += (f"Último escaneo ({e['perfil']}, {e['origen']}) {time.strftime('%d/%m %H:%M', time.localtime(e['fin'] or 0))}: "
                f"{e['hosts']} equipos, {e['puertos_abiertos']} puertos abiertos. ")
    lineas = [f"[{h['gravedad'].upper()}] {h['titulo']}. {h['detalle']} {h['recomendacion']}".strip()
              for h in inf["hallazgos"] if h["gravedad"] != "info"][:maximo]
    return cab + ("Hallazgos: " + " | ".join(lineas) if lineas else "Sin hallazgos relevantes.")
