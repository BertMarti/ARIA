"""Control parental: pausar internet o bloquear servicios por dispositivo, con horarios.

Todo se hace por DNS con SHIELD-DNS (Pi-hole v6), sin tocar el router:

- «Pausar internet» = el cliente (su IP) entra en el grupo `ARIA-pausa`, que tiene una regla de denegación
  por regex `.*` (todos los dominios). Pi-hole contesta 0.0.0.0 a todo lo que ese dispositivo pregunte.
- «Bloquear un servicio» = el cliente entra en el grupo `ARIA-svc-<servicio>`, cuya regla de denegación por
  regex agrupa los dominios del servicio (lista curada en `SERVICIOS`).
- En Pi-hole un cliente solo pertenece a los grupos que se le indican: ARIA siempre incluye el 0 (Default)
  para que el dispositivo conserve el bloqueo de anuncios.

LIMITACIÓN (se le dice siempre al usuario): es solo DNS. No frena a un dispositivo con DNS fijo, con DNS
cifrado (DoH/DoT, «DNS privado» de Android, iCloud Relay), con VPN, ni a los que usen el DNS secundario que
reparte el router (AdGuard). Tampoco corta lo que ya está en la caché DNS del dispositivo (unos minutos).

Estado deseado y reconciliación: lo que el administrador pide (pausas, servicios, horarios) vive en SQLite
(`control_*`). `reconciliar()` recalcula desde cero qué debe estar aplicado AHORA (pausas vigentes + horarios
activos a esta hora + servicios) y deja Pi-hole igual: crea/actualiza/borra SOLO los clientes que ARIA creó
(comentario `ARIA-control:<clave>`). Nunca toca clientes, grupos, listas ni reglas ajenos. Es idempotente y
no depende de memoria: tras un reinicio el siguiente tick lo deja todo bien. Los dispositivos se guardan por su
clave del inventario (`red_inventario`), y la IP actual se resuelve al aplicar (si cambia, se mueve el cliente).

Seguridad: solo dispositivos del inventario dentro de la LAN; nunca el router, la Raspberry ni las IP de
`ARIA_CONTROL_PROTEGIDOS`. No existe ninguna acción «para todos»: toda operación lleva una clave concreta.
"""
import asyncio
import ipaddress
import json
import logging
import re
import time
import unicodedata
from contextlib import closing
from datetime import datetime

from . import avisos, config, db, red, shield, tiempo

log = logging.getLogger("aria.control")

GRUPO_PAUSA = "ARIA-pausa"
PREFIJO_SERVICIO = "ARIA-svc-"
MARCA = "ARIA-control:"          # comentario de los clientes y reglas creados por ARIA
REGEX_PAUSA = ".*"
TICK_S = 30
REFRESCO_IP_S = 120
MAX_PAUSA_MIN = 7 * 24 * 60
MAX_HORARIOS_POR_DISPOSITIVO = 12

LIMITACION = ("Solo bloquea por DNS (SHIELD-DNS). No frena a un dispositivo con DNS fijo, con DNS cifrado (DoH/DoT, "
              "«DNS privado» de Android, iCloud Relay) o con VPN, ni a los que usan el DNS secundario que reparte el "
              "router (AdGuard). Los cambios tardan unos minutos en notarse por la caché DNS del dispositivo.")

LIMITACION_CORTA = ("Es un bloqueo por DNS: si el dispositivo usa DNS propio, DNS cifrado o VPN, podría seguir con "
                    "conexión.")

DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]

# Servicios curados: id -> (nombre, dominios). Cada dominio cubre también sus subdominios.
SERVICIOS: dict = {
    "tiktok": ("TikTok", ["tiktok.com", "tiktokv.com", "tiktokcdn.com", "tiktokcdn-eu.com", "tiktokcdn-us.com",
                          "byteoversea.com", "ibytedtos.com", "ibyteimg.com", "muscdn.com", "musical.ly",
                          "ttwstatic.com"]),
    "youtube": ("YouTube", ["youtube.com", "youtu.be", "ytimg.com", "googlevideo.com", "youtube-nocookie.com",
                            "youtubekids.com", "youtubei.googleapis.com", "youtube.googleapis.com",
                            "yt3.ggpht.com"]),
    "instagram": ("Instagram", ["instagram.com", "cdninstagram.com", "instagr.am"]),
    "facebook": ("Facebook", ["facebook.com", "facebook.net", "fb.com", "fb.me", "fbcdn.net", "fbsbx.com",
                              "messenger.com"]),
    "whatsapp": ("WhatsApp", ["whatsapp.com", "whatsapp.net", "wa.me"]),
    "snapchat": ("Snapchat", ["snapchat.com", "sc-cdn.net", "snapkit.com", "feelinsonice.com"]),
    "x": ("X (Twitter)", ["twitter.com", "x.com", "twimg.com", "t.co"]),
    "twitch": ("Twitch", ["twitch.tv", "ttvnw.net", "jtvnw.net", "twitchcdn.net", "twitchsvc.net"]),
    "discord": ("Discord", ["discord.com", "discordapp.com", "discordapp.net", "discord.gg", "discord.media"]),
    "fortnite": ("Fortnite / Epic Games", ["epicgames.com", "epicgames.dev", "fortnite.com", "unrealengine.com",
                                           "easyanticheat.net", "epicgames-download1.akamaized.net"]),
    "roblox": ("Roblox", ["roblox.com", "rbxcdn.com", "robloxlabs.com"]),
    "minecraft": ("Minecraft", ["minecraft.net", "mojang.com", "minecraftservices.com"]),
    "steam": ("Steam", ["steampowered.com", "steamcommunity.com", "steamstatic.com", "steamcontent.com",
                        "steamserver.net", "steamgames.com"]),
    "netflix": ("Netflix", ["netflix.com", "netflix.net", "nflxvideo.net", "nflximg.net", "nflximg.com",
                            "nflxext.com", "nflxso.net"]),
    "disneyplus": ("Disney+", ["disneyplus.com", "disney-plus.net", "dssott.com", "bamgrid.com",
                               "disneystreaming.com"]),
    "primevideo": ("Prime Video", ["primevideo.com", "amazonvideo.com", "aiv-cdn.net", "aiv-delivery.net",
                                   "pv-cdn.net"]),
    # No es una app: son los servidores de DNS cifrado (DoT/DoH, «DNS privado» de Android, Private Relay de iCloud).
    # Bloquearlos obliga al dispositivo a usar el DNS de casa (SHIELD-DNS) y así no se salta el bloqueador ni el
    # control parental. Un dispositivo con un servidor de DNS privado puesto A MANO se queda sin DNS hasta que lo
    # cambie a «automático»; por eso es opcional y por dispositivo.
    "dns-privado": ("DNS privado / DoH", ["dns.google", "dns.adguard.com", "dns.adguard-dns.com",
                                          "dns-unfiltered.adguard.com", "family.adguard-dns.com", "cloudflare-dns.com",
                                          "one.one.one.one", "dns.quad9.net", "dns9.quad9.net", "dns10.quad9.net",
                                          "dns11.quad9.net", "dns.nextdns.io", "doh.opendns.com",
                                          "doh.familyshield.opendns.com", "doh.cleanbrowsing.org", "dns.mullvad.net",
                                          "dns.controld.com", "doh.dns.sb", "dns.alidns.com", "doh.pub",
                                          "mask.icloud.com", "mask-h2.icloud.com", "use-application-dns.net"]),
}
_SINONIMOS = {"dns privado": "dns-privado", "doh": "dns-privado", "dns cifrado": "dns-privado",
              "dns seguro": "dns-privado", "tik tok": "tiktok", "tiktoks": "tiktok", "yt": "youtube", "you tube": "youtube", "insta": "instagram",
              "ig": "instagram", "face": "facebook", "fb": "facebook", "feisbuk": "facebook", "wasap": "whatsapp",
              "whats app": "whatsapp", "wa": "whatsapp", "snap": "snapchat", "twitter": "x", "tuiter": "x",
              "epic": "fortnite", "epic games": "fortnite", "epicgames": "fortnite", "fortnait": "fortnite",
              "disney": "disneyplus", "disney+": "disneyplus", "disney plus": "disneyplus", "prime": "primevideo",
              "prime video": "primevideo", "amazon prime": "primevideo", "amazon prime video": "primevideo"}


class ControlError(Exception):
    """Error legible (en español) para la interfaz, Telegram o el modelo."""


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn")


def servicio_id(texto: str) -> str | None:
    """«TikTok», «tik tok», «epic», «Disney+»... -> id del catálogo, o None."""
    t = " ".join(_sin_tildes(texto).split())
    if t in SERVICIOS:
        return t
    t = _SINONIMOS.get(t, t)
    if t in SERVICIOS:
        return t
    for sid, (nombre, _) in SERVICIOS.items():
        if _sin_tildes(nombre) == t:
            return sid
    return None


def catalogo() -> list:
    return [{"id": sid, "nombre": n} for sid, (n, _) in SERVICIOS.items()]


def nombre_servicio(sid: str) -> str:
    return SERVICIOS[sid][0] if sid in SERVICIOS else sid


def regex_servicio(sid: str) -> str:
    """`(^|\\.)(a\\.com|b\\.net)$`: el dominio y sus subdominios (Pi-hole ignora mayúsculas en los regex)."""
    doms = "|".join(d.replace(".", r"\.") for d in SERVICIOS[sid][1])
    return r"(^|\.)(" + doms + r")$"


def nombre_grupo(sid: str) -> str:
    return PREFIJO_SERVICIO + sid


# --- Base de datos -----------------------------------------------------------------------------------------
def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS control_pausas (
                clave TEXT PRIMARY KEY, hasta REAL, creado REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS control_servicios (
                clave TEXT NOT NULL, servicio TEXT NOT NULL, creado REAL NOT NULL, PRIMARY KEY (clave, servicio));
            CREATE TABLE IF NOT EXISTS control_horarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT, clave TEXT NOT NULL, servicio TEXT,
                dias TEXT NOT NULL, desde TEXT NOT NULL, hasta TEXT NOT NULL, creado REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_control_horarios ON control_horarios(clave);
            CREATE TABLE IF NOT EXISTS control_horarios_estado (
                id INTEGER PRIMARY KEY, activo INTEGER NOT NULL DEFAULT 0);
        """)


# --- Dispositivos: validación y resolución ----------------------------------------------------------------------
def protegidas() -> set:
    """IP que no se pueden pausar ni bloquear jamás: router, Raspberry y las de ARIA_CONTROL_PROTEGIDOS."""
    return {i for i in (config.ROUTER_IP, config.LAN_IP, "127.0.0.1") if i} | set(config.CONTROL_PROTEGIDOS)


def _ip_valida(ip: str) -> bool:
    """Una dirección IPv4 concreta de la LAN (ni red, ni difusión, ni rangos)."""
    try:
        a = ipaddress.ip_address(ip)
        red_ = ipaddress.ip_network(config.RED_PERMITIDA)
    except ValueError:
        return False
    return a.version == 4 and a in red_ and a != red_.network_address and a != red_.broadcast_address


def _fila(clave: str):
    with closing(db._con()) as con:
        return con.execute("SELECT clave, ip, nombre, fabricante, alias, mac, conocido FROM red_inventario WHERE clave=?",
                           (clave,)).fetchone()


def nombre_de(r) -> str:
    return (r["alias"] or r["nombre"] or r["fabricante"] or r["ip"] or r["clave"]) if r else "dispositivo"


def comprobar_dispositivo(clave: str):
    """Lista blanca: solo dispositivos del inventario, en la LAN y que no estén protegidos. Devuelve su fila."""
    r = _fila(clave) if isinstance(clave, str) and clave else None
    if not r:
        raise ControlError("No encuentro ese dispositivo en el inventario de la red.")
    if not r["ip"] or not _ip_valida(r["ip"]):
        raise ControlError("Ese dispositivo no tiene una IP válida de la red de casa.")
    if r["ip"] in protegidas():
        raise ControlError(f"«{nombre_de(r)}» ({r['ip']}) es parte de la infraestructura (router o Raspberry): "
                           "no se puede pausar ni bloquear.")
    return r


_ARTICULOS = re.compile(r"^(el|la|los|las|mi|mis|tu|su|un|una|del|de la)\s+")


def resolver(texto: str) -> str:
    """Alias, nombre, IP o MAC (como `red.buscar_clave`) y, si no es exacto, una coincidencia única por alias o
    nombre sin tildes. Devuelve la clave del inventario o lanza ControlError con la lista de candidatos."""
    clave = red.buscar_clave(texto)
    if clave:
        return clave
    t = " ".join(_sin_tildes(texto).split())
    while _ARTICULOS.match(t):
        t = _ARTICULOS.sub("", t, count=1)
    if not t:
        raise ControlError("¿Qué dispositivo? Dime su nombre, IP o MAC.")
    clave = red.buscar_clave(t)
    if clave:
        return clave
    with closing(db._con()) as con:
        filas = con.execute("SELECT clave, ip, nombre, alias FROM red_inventario").fetchall()
    exactas = [f for f in filas if t in (_sin_tildes(f["alias"]), _sin_tildes(f["nombre"]))]
    if len(exactas) == 1:
        return exactas[0]["clave"]
    parciales = exactas or [f for f in filas if t in _sin_tildes(f["alias"]) or t in _sin_tildes(f["nombre"])]
    if len(parciales) == 1:
        return parciales[0]["clave"]
    if parciales:
        raise ControlError("Encajan varios dispositivos: " + "; ".join(
            f"{f['alias'] or f['nombre']} ({f['ip']})" for f in parciales[:6]) + ". Dime cuál (nombre exacto o IP).")
    raise ControlError(f"No encuentro ningún dispositivo llamado «{texto}» en el inventario.")


# --- Estado deseado (SQLite) ---------------------------------------------------------------------------------
def pausar(clave: str, minutos: int | None = None, ahora: float | None = None) -> dict:
    """Pausa el internet del dispositivo `minutos` minutos (None = hasta que se reanude)."""
    comprobar_dispositivo(clave)
    ahora = time.time() if ahora is None else ahora
    if minutos is not None:
        if isinstance(minutos, bool) or not isinstance(minutos, (int, float)) or not 1 <= minutos <= MAX_PAUSA_MIN:
            raise ControlError(f"La pausa debe durar entre 1 minuto y {MAX_PAUSA_MIN // 1440} días (o ser indefinida).")
        minutos = int(minutos)
    hasta = ahora + minutos * 60 if minutos else None
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO control_pausas (clave, hasta, creado) VALUES (?,?,?) "
                    "ON CONFLICT(clave) DO UPDATE SET hasta=excluded.hasta, creado=excluded.creado", (clave, hasta, ahora))
    return {"clave": clave, "hasta": hasta}


def reanudar(clave: str) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM control_pausas WHERE clave=?", (clave,)).rowcount > 0


def bloquear_servicio(clave: str, servicio: str) -> str:
    comprobar_dispositivo(clave)
    sid = servicio_id(servicio)
    if not sid:
        raise ControlError("No conozco ese servicio. Disponibles: " + ", ".join(n for n, _ in SERVICIOS.values()) + ".")
    with closing(db._con()) as con, con:
        con.execute("INSERT OR IGNORE INTO control_servicios (clave, servicio, creado) VALUES (?,?,?)",
                    (clave, sid, time.time()))
    return sid


def desbloquear_servicio(clave: str, servicio: str) -> str:
    sid = servicio_id(servicio)
    if not sid:
        raise ControlError("No conozco ese servicio. Disponibles: " + ", ".join(n for n, _ in SERVICIOS.values()) + ".")
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM control_servicios WHERE clave=? AND servicio=?", (clave, sid))
    return sid


def quitar_servicios(clave: str) -> int:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM control_servicios WHERE clave=?", (clave,)).rowcount


def _hhmm(v) -> str:
    if isinstance(v, str) and len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit() \
            and int(v[:2]) < 24 and int(v[3:]) < 60:
        return v
    raise ControlError("La hora debe tener el formato HH:MM (por ejemplo 23:00).")


def _minutos(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def crear_horario(clave: str, servicio: str | None, dias, desde: str, hasta: str) -> dict:
    """`servicio` vacío = sin internet. `dias`: lista de 0 (lunes) a 6 (domingo) en que EMPIEZA el tramo; si
    `hasta` es menor que `desde` el tramo cruza la medianoche (23:00–08:00)."""
    comprobar_dispositivo(clave)
    sid = None
    if servicio:
        sid = servicio_id(servicio)
        if not sid:
            raise ControlError("No conozco ese servicio.")
    if not isinstance(dias, (list, tuple)) or not dias or any(
            isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6 for d in dias):
        raise ControlError("Elige al menos un día de la semana.")
    dias = sorted(set(dias))
    desde, hasta = _hhmm(desde), _hhmm(hasta)
    if desde == hasta:
        raise ControlError("La hora de inicio y la de fin no pueden ser la misma.")
    with closing(db._con()) as con, con:
        if con.execute("SELECT COUNT(*) FROM control_horarios WHERE clave=?", (clave,)).fetchone()[0] \
                >= MAX_HORARIOS_POR_DISPOSITIVO:
            raise ControlError(f"Máximo {MAX_HORARIOS_POR_DISPOSITIVO} horarios por dispositivo.")
        hid = con.execute("INSERT INTO control_horarios (clave, servicio, dias, desde, hasta, creado) VALUES (?,?,?,?,?,?)",
                          (clave, sid, ",".join(map(str, dias)), desde, hasta, time.time())).lastrowid
    return {"id": hid}


def borrar_horario(hid: int) -> bool:
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM control_horarios_estado WHERE id=?", (hid,))
        return con.execute("DELETE FROM control_horarios WHERE id=?", (hid,)).rowcount > 0


def _horarios(clave: str | None = None) -> list:
    with closing(db._con()) as con:
        filas = con.execute("SELECT * FROM control_horarios" + (" WHERE clave=?" if clave else "") + " ORDER BY id",
                            (clave,) if clave else ()).fetchall()
    return [{"id": f["id"], "clave": f["clave"], "servicio": f["servicio"],
             "dias": [int(d) for d in f["dias"].split(",") if d != ""], "desde": f["desde"], "hasta": f["hasta"]}
            for f in filas]


def horario_activo(h: dict, ref: datetime) -> bool:
    """¿Está el horario en marcha a esa hora local? Los días son los de INICIO del tramo."""
    m, d0, d1 = ref.hour * 60 + ref.minute, _minutos(h["desde"]), _minutos(h["hasta"])
    hoy, ayer = ref.weekday(), (ref.weekday() - 1) % 7
    if d0 < d1:
        return hoy in h["dias"] and d0 <= m < d1
    return (hoy in h["dias"] and m >= d0) or (ayer in h["dias"] and m < d1)


def texto_dias(dias: list) -> str:
    d = sorted(dias)
    if d == [0, 1, 2, 3, 4]:
        return "de lunes a viernes"
    if d == [5, 6]:
        return "sábados y domingos"
    if d == list(range(7)):
        return "todos los días"
    return ", ".join(DIAS_CORTOS[i] for i in d)


def texto_horario(h: dict) -> str:
    que = f"sin {nombre_servicio(h['servicio'])}" if h["servicio"] else "sin internet"
    return f"{que} {texto_dias(h['dias'])} de {h['desde']} a {h['hasta']}"


def _purgar_caducadas(ahora: float) -> None:
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM control_pausas WHERE hasta IS NOT NULL AND hasta<=?", (ahora,))


def _ref(ahora: float | None) -> datetime:
    return datetime.fromtimestamp(time.time() if ahora is None else ahora, tiempo.zona())


def calcular_deseado(ahora: float | None = None) -> dict:
    """Qué debe estar aplicado ahora: {clave: {pausa, pausa_hasta, servicios:set, horarios:[ids activos],
    por_horario_internet: bool}}. Solo salen los dispositivos con algo aplicado."""
    ahora = time.time() if ahora is None else ahora
    ref = _ref(ahora)
    _purgar_caducadas(ahora)
    out: dict = {}

    def x(clave):
        return out.setdefault(clave, {"pausa": False, "pausa_hasta": None, "servicios": set(), "horarios": [],
                                      "por_horario": False})
    with closing(db._con()) as con:
        for r in con.execute("SELECT clave, hasta FROM control_pausas"):
            d = x(r["clave"])
            d["pausa"], d["pausa_hasta"] = True, r["hasta"]
        for r in con.execute("SELECT clave, servicio FROM control_servicios"):
            x(r["clave"])["servicios"].add(r["servicio"])
    for h in _horarios():
        if horario_activo(h, ref):
            d = x(h["clave"])
            d["horarios"].append(h["id"])
            if h["servicio"]:
                d["servicios"].add(h["servicio"])
            else:
                d["pausa"], d["por_horario"] = True, True
    return out


def estado(clave: str | None = None, ahora: float | None = None) -> list:
    """Estado de control de los dispositivos con algo configurado (o solo de `clave`, aunque esté libre)."""
    ahora = time.time() if ahora is None else ahora
    deseado = calcular_deseado(ahora)
    horarios = _horarios()
    with closing(db._con()) as con:
        pausas = {r["clave"] for r in con.execute("SELECT clave FROM control_pausas")}
        manual: dict = {}
        for r in con.execute("SELECT clave, servicio FROM control_servicios"):
            manual.setdefault(r["clave"], set()).add(r["servicio"])
    claves = set(deseado) | {h["clave"] for h in horarios} | pausas | set(manual)
    if clave:
        claves = {clave}
    salida = []
    for c in sorted(claves):
        r = _fila(c)
        d = deseado.get(c) or {"pausa": False, "pausa_hasta": None, "servicios": set(), "horarios": [], "por_horario": False}
        salida.append({
            "clave": c, "nombre": nombre_de(r) if r else c, "ip": r["ip"] if r else None,
            "protegido": bool(r and r["ip"] in protegidas()),
            "pausado": d["pausa"], "pausa_hasta": d["pausa_hasta"], "pausa_manual": c in pausas,
            "por_horario": d["por_horario"],
            "servicios_bloqueados": sorted(d["servicios"]),
            "servicios_manuales": sorted(manual.get(c, set())),
            "horarios": [{**h, "texto": texto_horario(h), "activo": h["id"] in d["horarios"]}
                         for h in horarios if h["clave"] == c]})
    return salida


def texto_estado(e: dict) -> str:
    """Una línea en español con el estado de un dispositivo."""
    partes = []
    if e["pausado"]:
        if e["pausa_manual"]:
            partes.append("sin internet " + (f"hasta las {datetime.fromtimestamp(e['pausa_hasta'], tiempo.zona()):%H:%M}"
                                            if e["pausa_hasta"] else "hasta que se reanude"))
        if e["por_horario"]:
            partes.append("sin internet por horario")
    if e["servicios_bloqueados"]:
        partes.append("sin " + ", ".join(nombre_servicio(s) for s in e["servicios_bloqueados"]))
    pendientes = [h for h in e["horarios"] if not h["activo"]]
    if pendientes:
        partes.append(f"{len(pendientes)} horario(s) programado(s)")
    return f"{e['nombre']}" + (f" ({e['ip']})" if e["ip"] else "") + ": " + ("; ".join(partes) if partes else "libre")


# --- Aplicación en Pi-hole (reconciliación) ---------------------------------------------------------------------------
_lock = asyncio.Lock()
_ultimo: dict = {"ts": None, "ok": None, "error": None, "gestionados": 0, "ips_nuevas": 0}
_ult_refresco = 0.0


def _inventario_ips() -> dict:
    with closing(db._con()) as con:
        return {r["clave"]: r["ip"] for r in con.execute("SELECT clave, ip FROM red_inventario")}


async def _asegurar_regla(regex: str, gid: int, comentario: str, doms: dict) -> None:
    """La regla de denegación `regex` debe existir, activa y SOLO en el grupo `gid` (nunca el 0 = Default).
    Se crea desactivada, se comprueba su grupo y solo entonces se activa; si no es de ARIA no se toca."""
    if gid == 0:
        raise ControlError("Seguridad: una regla de ARIA nunca puede ir en el grupo Default.")
    dom = doms.get(regex)
    if dom is None:
        nuevo = await shield.crear_dominio_regex_deny(regex, [gid], comentario, False)
        if sorted(nuevo.get("groups") or []) != [gid]:
            await shield.borrar_dominio_regex_deny(regex)
            raise ControlError("SHIELD-DNS no asignó la regla al grupo esperado; la he borrado por seguridad.")
    elif not str(dom.get("comment") or "").startswith(MARCA):
        raise ControlError(f"En SHIELD-DNS ya hay una regla ajena igual ({regex[:30]}); no la toco.")
    elif sorted(dom.get("groups") or []) == [gid] and dom.get("enabled"):
        return
    ok = await shield.actualizar_dominio_regex_deny(regex, [gid], comentario, True)
    if sorted(ok.get("groups") or []) != [gid]:
        await shield.actualizar_dominio_regex_deny(regex, [gid], comentario, False)
        raise ControlError("SHIELD-DNS no dejó la regla en el grupo esperado; la he desactivado por seguridad.")


async def _asegurar_grupos(nombres: set) -> dict:
    """Crea (si faltan) los grupos y reglas de ARIA que se van a usar. Devuelve {nombre de grupo: id}."""
    existentes = {g["name"]: g["id"] for g in await shield.grupos()}
    ids = {}
    for n in sorted(nombres):
        if n not in existentes:
            g = await shield.crear_grupo(n, MARCA + "grupo creado por ARIA (control parental)")
            existentes[n] = g.get("id")
        if not isinstance(existentes[n], int) or existentes[n] == 0:
            raise ControlError("SHIELD-DNS devolvió un grupo no válido.")
        ids[n] = existentes[n]
    doms = {d["domain"]: d for d in await shield.dominios_regex_deny()}
    for n, gid in ids.items():
        if n == GRUPO_PAUSA:
            await _asegurar_regla(REGEX_PAUSA, gid, MARCA + "pausa de internet", doms)
        else:
            sid = n[len(PREFIJO_SERVICIO):]
            await _asegurar_regla(regex_servicio(sid), gid, MARCA + nombre_servicio(sid), doms)
    return ids


async def _refrescar_ips(ahora: float) -> None:
    global _ult_refresco
    if ahora - _ult_refresco < REFRESCO_IP_S:
        return
    _ult_refresco = ahora
    try:
        await red.dispositivos()
    except Exception:  # noqa: BLE001 - sin Pi-hole se usa la IP del inventario
        log.warning("No se pudo refrescar el inventario de red; uso la última IP conocida")


async def reconciliar(ahora: float | None = None, refrescar: bool = False) -> dict:
    """Deja SHIELD-DNS exactamente como pide el estado deseado. Idempotente. Devuelve un resumen."""
    if not config.CONTROL:
        return {"ok": False, "error": "El control parental está desactivado (ARIA_CONTROL=0)."}
    if not shield.configurado():
        return {"ok": False, "error": "SHIELD-DNS no está conectado a ARIA."}
    ahora = time.time() if ahora is None else ahora
    async with _lock:
        try:
            resumen = await _reconciliar(ahora, refrescar)
        except (shield.ShieldError, ControlError) as e:
            _ultimo.update(ts=ahora, ok=False, error=str(e))
            return {"ok": False, "error": str(e)}
        _ultimo.update(ts=ahora, ok=not resumen["errores"], error="; ".join(resumen["errores"]) or None,
                       gestionados=resumen["gestionados"])
        return {"ok": not resumen["errores"], "error": _ultimo["error"], **resumen}


async def _reconciliar(ahora: float, refrescar: bool) -> dict:
    deseado = {c: d for c, d in (await asyncio.to_thread(calcular_deseado, ahora)).items()
               if d["pausa"] or d["servicios"]}
    if refrescar and deseado:
        await _refrescar_ips(ahora)
    ips = await asyncio.to_thread(_inventario_ips)
    errores, hecho = [], {"creados": 0, "movidos": 0, "actualizados": 0, "borrados": 0}

    # 1. A qué IP corresponde cada dispositivo con algo aplicado, y a qué grupos debe pertenecer.
    nombres = set()
    destino: dict = {}                                  # ip -> (clave, set de nombres de grupo)
    for clave, d in deseado.items():
        ip = ips.get(clave)
        if not ip or not _ip_valida(ip) or ip in protegidas():
            errores.append(f"{clave}: sin IP aplicable (o protegida); no se aplica")
            continue
        grupos_ = ({GRUPO_PAUSA} if d["pausa"] else set()) | {nombre_grupo(s) for s in d["servicios"] if s in SERVICIOS}
        if ip in destino:                               # dos claves con la misma IP: gana la unión
            grupos_ |= destino[ip][1]
        destino[ip] = (clave, grupos_)
        nombres |= grupos_

    # 2. Grupos y reglas necesarios (solo si hace falta algo).
    ids = await _asegurar_grupos(nombres) if nombres else {}

    # 3. Clientes: alta / cambio de grupos / baja. Solo los que llevan la marca de ARIA.
    clientes = await shield.clientes()
    por_ip = {c["client"]: c for c in clientes}
    propios = {c["client"]: c for c in clientes if str(c.get("comment") or "").startswith(MARCA)}
    for ip, (clave, gs) in destino.items():
        quiero = sorted({0} | {ids[g] for g in gs})
        c = por_ip.get(ip)
        comentario = MARCA + clave
        if c is None:
            await shield.crear_cliente(ip, quiero, comentario)
            hecho["creados"] += 1
        elif ip in propios:
            if sorted(c.get("groups") or []) != quiero or c.get("comment") != comentario:
                await shield.actualizar_cliente(ip, quiero, comentario)
                hecho["actualizados"] += 1
        else:
            errores.append(f"{ip}: ya es un cliente configurado a mano en SHIELD-DNS; no lo toco")
    for ip in propios:
        if ip not in destino:                           # ya no toca (reanudado, caducado, IP cambiada...)
            await shield.borrar_cliente(ip)
            hecho["borrados"] += 1
    return {"errores": errores, "gestionados": len(destino), **hecho}


# --- Avisos de horario y planificador -------------------------------------------------------------------------------------
async def transiciones(ahora: float | None = None) -> list:
    """Avisa cuando un horario empieza o termina (una vez por cambio; el último estado avisado está en SQLite)."""
    ahora = time.time() if ahora is None else ahora
    ref = _ref(ahora)

    def leer():
        hs = _horarios()
        with closing(db._con()) as con:
            prev = {r["id"]: bool(r["activo"]) for r in con.execute("SELECT id, activo FROM control_horarios_estado")}
        return hs, prev
    hs, prev = await asyncio.to_thread(leer)
    avisados = []
    for h in hs:
        ahora_activo = horario_activo(h, ref)
        if ahora_activo == prev.get(h["id"], False):
            continue

        def guardar(h=h, a=ahora_activo):
            with closing(db._con()) as con, con:
                con.execute("INSERT INTO control_horarios_estado (id, activo) VALUES (?,?) "
                            "ON CONFLICT(id) DO UPDATE SET activo=excluded.activo", (h["id"], int(a)))
        await asyncio.to_thread(guardar)
        r = await asyncio.to_thread(_fila, h["clave"])
        que = f"sin {nombre_servicio(h['servicio'])}" if h["servicio"] else "sin internet"
        texto = (f"Control parental: {nombre_de(r)} se queda {que} (horario de {h['desde']} a {h['hasta']})."
                 if ahora_activo else
                 f"Control parental: termina el horario de {nombre_de(r)} {que}; vuelve a tener acceso.")
        avisados.append(texto)
        await avisos.emitir("control", "info", texto, "red")
    return avisados


async def tick(ahora: float | None = None) -> dict:
    ahora = time.time() if ahora is None else ahora
    try:
        await transiciones(ahora)
    except Exception:  # noqa: BLE001 - un fallo de avisos no debe impedir el bloqueo
        log.exception("Falló el aviso de horarios de control parental")
    return await reconciliar(ahora, refrescar=True)


async def bucle(retraso: float = 20) -> None:
    await asyncio.sleep(retraso)
    fallo_previo = False
    while True:
        try:
            r = await tick()
            if not r.get("ok") and not fallo_previo:
                log.warning("Control parental sin aplicar: %s", r.get("error"))
            fallo_previo = not r.get("ok")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Fallo en el planificador de control parental")
        await asyncio.sleep(TICK_S)


def resumen_api(ahora: float | None = None) -> dict:
    return {"servicios": catalogo(), "limitacion": LIMITACION, "protegidas": sorted(protegidas()), "activo": config.CONTROL,
            "conectado": shield.configurado(),
            "aplicado": {k: _ultimo[k] for k in ("ts", "ok", "error")},
            "dispositivos": estado(None, ahora)}
