"""Chequeos iniciales del motor de avisos. Cada uno devuelve una lista de `Problema` activos o None
si no puede saberlo (integración sin configurar, sin datos). Ninguno usa el socket de Docker."""
import asyncio
from contextlib import closing

import httpx

from . import avisos, cerebros, config, db, services, sistema, telemetria, vpn, vpn_ubicaciones
from .avisos import Chequeo, Problema

TEMP_MAX = 75.0
DISCO_MAX = 85.0
RAM_MIN_DISPONIBLE = 5.0
SIN_NUBE_S = 30 * 60


# --- Servicios del laboratorio ----------------------------------------------------------------------
async def shield_dns() -> list:
    e = await services.estado()
    s = e["shield_dns"]
    if s["dns_ok"] and s["web_ok"]:
        return []
    if not s["dns_ok"] and not s["web_ok"]:
        return [Problema("caido", "SHIELD-DNS está caído: ni responde el DNS ni su panel. Sin él, la casa puede "
                                  "quedarse sin resolver nombres.")]
    if not s["dns_ok"]:
        return [Problema("dns", "SHIELD-DNS no responde a consultas DNS (el panel sí está activo).")]
    return [Problema("web", "El panel de SHIELD-DNS no responde (el DNS sí funciona).", "aviso")]


async def heimdall() -> list:
    e = await services.estado()
    return [] if e["heimdall"]["web_ok"] else [Problema("caido", "HEIMDALL (la VPN) no responde.")]


async def tunel() -> list | None:
    """Acceso desde fuera: el dominio público debe responder 200 o 302 (Cloudflare Access redirige al login).
    Un 5xx (p. ej. 530/1033) o un fallo de conexión indica que el túnel de Cloudflare está caído."""
    url = config.URL_PUBLICA
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as c:
            r = await c.get(url, headers={"User-Agent": "ARIA-avisos/1"})
        estado = r.status_code
    except httpx.HTTPError as e:
        estado = type(e).__name__
    if estado in (200, 302):
        return []
    return [Problema("caido", f"No se puede entrar en ARIA desde fuera ({config.URL_PUBLICA.split('//')[-1]} "
                              f"responde {estado}). Revisa el túnel de Cloudflare (contenedor cloudflared).")]


# --- Red y seguridad --------------------------------------------------------------------------------
async def dispositivos_nuevos() -> list | None:
    from . import red, shield
    if not shield.configurado():
        return None
    ds = await red.dispositivos()
    return [Problema(d["clave"], "Dispositivo desconocido en la red: "
                     f"{d.get('nombre') or d.get('fabricante') or 'sin nombre'} ({d['ip']}). Si es tuyo, márcalo "
                     "como conocido en Red.") for d in ds if not d.get("conocido")]


_ultimo_escaneo = {"id": None}


def _inventario() -> dict:
    with closing(db._con()) as con:
        try:
            return {r["ip"]: dict(r) for r in con.execute("SELECT * FROM red_inventario")}
        except Exception:  # noqa: BLE001 - tabla aún sin crear
            return {}


async def hallazgos_graves() -> list | None:
    """Hallazgos de gravedad alta del último escaneo (solo se recalcula cuando hay un escaneo nuevo)."""
    from . import escaneo, seguridad
    res = await asyncio.to_thread(escaneo.ultimo)
    if not res or res.get("error"):
        return None
    if res.get("id") == _ultimo_escaneo["id"]:
        return []
    anterior = await asyncio.to_thread(escaneo.anterior_a, res.get("id"))
    hall = seguridad.hallazgos_de_escaneo(res, anterior, await asyncio.to_thread(_inventario))
    _ultimo_escaneo["id"] = res.get("id")
    return [Problema(f"{h['tipo']}:{h.get('ip') or ''}:{h['titulo']}"[:200],
                     f"Seguridad: {h['titulo']}. {h.get('recomendacion') or ''}".strip())
            for h in hall if h.get("gravedad") == "alta"]


# --- Copia, sistema, VPN, cerebros ---------------------------------------------------------------------
async def copia() -> list | None:
    from . import briefing
    c = await asyncio.to_thread(briefing.ultima_copia)
    if not c.get("disponible"):
        return None
    return [Problema("antigua", f"La última copia de seguridad fuera de casa fue {c['hace']} (más de "
                                f"{briefing.COPIA_ANTIGUA_H} h). Revisa sistema/copia-diaria.sh.")] if c.get("antigua") else []


async def temperatura() -> list | None:
    t = sistema.temperatura()
    if t is None:
        return None
    return [Problema("alta", f"La Raspberry está a {str(t).replace('.', ',')} °C (más de {TEMP_MAX:.0f} °C).")] if t > TEMP_MAX else []


async def disco() -> list | None:
    d = sistema.disco()
    if not d:
        return None
    return [Problema("lleno", f"El disco está al {str(d['porcentaje']).replace('.', ',')} % (más del {DISCO_MAX:.0f} %).")] \
        if d["porcentaje"] > DISCO_MAX else []


async def ram() -> list | None:
    m = sistema.memoria()
    if not m:
        return None
    libre = m["disponible"] * 100 / m["total"]
    return [Problema("baja", f"Queda poca RAM disponible en la Raspberry ({libre:.1f} %).".replace(".", ",", 1))] \
        if libre < RAM_MIN_DISPONIBLE else []


async def vpn_conexiones() -> list | None:
    if not vpn.configurado():
        return None
    try:
        cl = await vpn.listar()
    except vpn.VpnError:
        return None
    return [Problema(str(c["id"]), f"VPN: «{c['nombre']}» se ha conectado.") for c in cl if c.get("conectado")]


def _nube_configurada() -> list:
    orden, apagados = cerebros.configuracion()
    return [p for p in cerebros.PROVEEDORES.values() if p.nube and p.tiene_clave() and p.id not in apagados]


async def cerebros_caidos() -> list | None:
    """Todos los cerebros en la nube en espera por fallos: solo responde el local. Con `confirmaciones`
    = 30 y un intervalo de 60 s, se avisa tras unos 30 minutos seguidos."""
    if not _nube_configurada():
        return None  # sin claves de la nube: lo normal es el local, no hay nada que avisar
    if cerebros.hay_nube():
        return []
    return [Problema("solo_local", "Los cerebros en la nube llevan más de 30 minutos fallando: solo responde el "
                                   "cerebro local (más lento). Revisa las claves y los límites en Ajustes → Cerebros.")]


async def telemetria_picos() -> list | None:
    try:
        d = await asyncio.to_thread(telemetria.leer)
    except RuntimeError:
        return None
    u = telemetria.estados(d)
    problemas = []
    if u["cpu"]["activo"]:
        problemas.append(Problema("cpu", "La CPU de la Raspberry lleva dos minutos por encima del 90 %."))
    for c in u["contenedores"]:
        if c["activo"]:
            problemas.append(Problema(c["nombre"], f"El contenedor {c['nombre']} está consumiendo demasiados recursos."))
    return problemas


def registrar() -> None:
    """Registra los chequeos iniciales (idempotente)."""
    for c in (
        Chequeo("shield_dns", "servicios", "grave", shield_dns, intervalo_s=60, confirmaciones=2,
                texto_ok="SHIELD-DNS vuelve a funcionar.", enlace="control"),
        Chequeo("heimdall", "servicios", "grave", heimdall, intervalo_s=60, confirmaciones=2,
                texto_ok="HEIMDALL (la VPN) vuelve a responder.", enlace="control"),
        Chequeo("tunel", "tunel", "aviso", tunel, intervalo_s=300, confirmaciones=2,
                texto_ok="Se vuelve a poder entrar en ARIA desde fuera.", enlace="control"),
        Chequeo("dispositivo_nuevo", "dispositivo_nuevo", "aviso", dispositivos_nuevos, intervalo_s=600,
                evento=True, linea_base=True, enlace="red"),
        Chequeo("seguridad", "seguridad", "grave", hallazgos_graves, intervalo_s=900,
                evento=True, linea_base=True, enlace="seguridad"),
        Chequeo("copia", "copia", "aviso", copia, intervalo_s=1800, repetir_s=24 * 3600,
                texto_ok="La copia de seguridad fuera de casa vuelve a estar al día.", enlace="inicio"),
        Chequeo("temperatura", "sistema", "grave", temperatura, intervalo_s=60, confirmaciones=3, cooldown_s=3600,
                texto_ok="La temperatura de la Raspberry ha vuelto a la normalidad.", enlace="control"),
        Chequeo("disco", "sistema", "aviso", disco, intervalo_s=600, repetir_s=24 * 3600,
                texto_ok="El disco vuelve a tener espacio suficiente.", enlace="control"),
        Chequeo("ram", "sistema", "aviso", ram, intervalo_s=60, confirmaciones=3, cooldown_s=3600,
                texto_ok="La RAM de la Raspberry vuelve a estar holgada.", enlace="control"),
        Chequeo("vpn_conexion", "vpn_conexion", "info", vpn_conexiones, intervalo_s=60, cooldown_s=600,
                 linea_base=True, enlace="control"),
        Chequeo("vpn_ubicaciones", "vpn_ubicacion", "aviso", vpn_ubicaciones.comprobar, intervalo_s=120,
                 evento=True, enlace="control"),
        Chequeo("cerebros", "cerebros", "aviso", cerebros_caidos, intervalo_s=60, confirmaciones=SIN_NUBE_S // 60,
                 texto_ok="Los cerebros en la nube vuelven a responder.", enlace="ajustes"),
        # telemetria.estados ya exige dos minutos de CPU y cinco de contenedor; no duplicar la confirmación aquí.
        Chequeo("telemetria", "telemetria", "aviso", telemetria_picos, intervalo_s=60, confirmaciones=1,
                 texto_ok="Los picos del sistema han vuelto a la normalidad.", enlace="control"),
    ):
        avisos.registrar_chequeo(c)
