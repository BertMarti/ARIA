"""Agentes especializados («cerebros» con oficio): ARIA general, Finanzas, Redes y Seguridad.

Cada agente tiene un prompt en español, un conjunto de herramientas, los roles que pueden usarlo
y, opcionalmente, un cerebro preferido (id de `cerebros.PROVEEDORES`). La elección se hace:
  1. con el prefijo `@finanzas`, `@redes`, `@seguridad` o `@aria` en el mensaje (solo ese mensaje);
  2. con el selector de la cabecera del chat (se guarda en la conversación);
  3. si la conversación está en «aria», ARIA enruta sola: primero un filtro barato de palabras
     clave y, solo si hay empate entre agentes, una clasificación de una línea con el primer
     cerebro en la nube. Nunca se enruta a un agente que el rol del usuario no puede usar.
"""
import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from . import cerebros, config, tools

AUTO = "aria"


@dataclass(frozen=True)
class Agente:
    id: str
    nombre: str
    icono: str            # clave de icono que pinta la interfaz (svg en línea)
    descripcion: str
    prompt: str
    herramientas: frozenset
    roles: frozenset = frozenset({"admin", "usuario"})
    cerebro: str | None = None   # cerebro preferido (se pone el primero de la cadena si está disponible)
    palabras: tuple = field(default=())  # patrones del filtro de enrutado

    def publico(self) -> dict:
        return {"id": self.id, "nombre": self.nombre, "icono": self.icono, "descripcion": self.descripcion}


_COMUN = ("Responde siempre en español de España, de forma breve y clara. Usa las herramientas solo "
          "cuando haga falta un dato en vivo y no inventes sus resultados. ")

_BASE_ARIA = frozenset({
    "fecha_hora", "estado_servicios", "estado_bloqueador", "pausar_bloqueador", "reanudar_bloqueador",
    "dispositivos_vpn", "ubicaciones_vpn", "crear_dispositivo_vpn", "activar_dispositivo_vpn", "desactivar_dispositivo_vpn",
    "estado_sistema", "spotify_play", "spotify_pause", "spotify_siguiente", "spotify_anterior",
    "spotify_actual", "spotify_buscar_y_reproducir", "buscar_en_netflix",
    "recordar", "olvidar", "buscar_en_internet", "noticias", "tiempo",
    "recordatorio", "mis_recordatorios", "borrar_recordatorio", "resumir_enlace",
    "crear_rutina", "mis_rutinas", "borrar_rutina",
    "mapa_ir", "ruta", "sitios_cerca",
    "sistema_en_directo",
    "crear_evento", "mis_eventos", "borrar_evento", "anadir_cumpleanos", "proximos_cumpleanos",
    "mapa_ir", "ruta", "sitios_cerca"})
# Memoria personal y búsqueda web también para los especialistas (precios, avisos de seguridad, fabricantes...).
_COMUNES = frozenset({"fecha_hora", "recordar", "olvidar", "buscar_en_internet", "resumir_enlace",
                      "recordatorio", "mis_recordatorios", "borrar_recordatorio"})

FINANZAS_TOOLS = frozenset({"registrar_movimiento", "resumen_mes", "gastos_por_categoria", "comparar_meses",
                            "presupuesto", "estado_presupuestos", "buscar_movimientos"})
REDES_TOOLS = frozenset({"estado_red", "dispositivos_red", "dispositivos_nuevos", "marcar_dispositivo_conocido",
                         "medir_latencia", "test_velocidad", "pausar_internet", "reanudar_internet",
                         "bloquear_servicio", "desbloquear_servicio", "estado_control"})
SEGURIDAD_TOOLS = frozenset({"informe_seguridad", "escanear_red", "estado_escaneo", "bloqueos_por_cliente"})

AGENTES: dict = {a.id: a for a in (
    Agente("aria", "ARIA", "aria", "Asistente general; deriva a los especialistas cuando hace falta.",
           "", _BASE_ARIA),
    Agente("finanzas", "Finanzas", "finanzas", "Gastos, ingresos, categorías y presupuestos (solo tus datos).",
           "Eres el agente de Finanzas de ARIA, un asistente doméstico. Ayudas a la persona con SUS movimientos, "
           "categorías y presupuestos mensuales (cada usuario solo ve sus datos). " + _COMUN +
           "Las cantidades van en euros con coma decimal (12,50 €). Los gastos son importes negativos y los "
           "ingresos positivos. Si te piden apuntar un gasto, usa registrar_movimiento con importe negativo. "
           "Los meses se indican como AAAA-MM. No das asesoramiento de inversión: no eres un asesor financiero "
           "con licencia. No tienes acceso a bancos: los datos vienen de lo que el usuario apunta o importa en CSV.",
           FINANZAS_TOOLS | _COMUNES,
           palabras=(r"\bgast\w*", r"\bingres\w*", r"\bpresupuest\w*", r"\bfinanz\w*", r"\bdinero\b", r"\beuros?\b",
                     r"€", r"\bn[oó]mina\b", r"\bmovimientos?\b", r"\bahorr\w*", r"\bfactur\w*", r"\bcompr[ae]\w*",
                     r"\bpagu[eé]\b", r"\bpag(o|os|ado|ar)\b", r"\bcuenta bancaria\b", r"\bsupermercado\b")),
    Agente("redes", "Redes", "redes", "Dispositivos de la LAN, latencia, velocidad, DNS y VPN.",
           f"Eres el agente de Redes de ARIA. Conoces la red de casa (LAN {config.RED_PERMITIDA}, router {config.ROUTER_IP}, "
           f"Raspberry Pi {config.LAN_IP} con SHIELD-DNS (Pi-hole) y la VPN HEIMDALL (WireGuard)). " + _COMUN +
           "Explica los resultados de forma sencilla (ms, Mbps). El test de velocidad gasta datos y se limita "
           "a uno cada 10 minutos. Control parental (solo administrador): pausar_internet, reanudar_internet, "
           "bloquear_servicio, desbloquear_servicio y estado_control actúan sobre UN dispositivo; calcula los minutos "
           "(«una hora» = 60). Es un bloqueo por DNS: dilo si preguntan, porque un dispositivo con DNS propio, DNS "
           "cifrado o VPN puede seguir con conexión. Nunca hay una acción para todos los dispositivos, ni se puede "
           "pausar el router ni la Raspberry.",
           REDES_TOOLS | _COMUNES | {"estado_servicios", "estado_bloqueador", "dispositivos_vpn", "ubicaciones_vpn"},
           palabras=(r"\bred(es)?\b", r"\blan\b", r"\bwi-?fi\b", r"\blatencia\b", r"\bping\b", r"\bvelocidad\b",
                     r"\bmbps\b", r"\binternet\b", r"\brouter\b", r"\bdispositivos? (de|en) (la )?(casa|red)\b",
                     r"\bconectad\w+ a la red\b", r"\bdispositivos? nuevos?\b", r"\bfibra\b", r"\bip\b", r"\bcontrol parental\b", r"\bsin internet\b",
                     r"\b(paus\w+|cort\w+|bloque\w+|desbloque\w+|reanud\w+)\b.{0,40}\b(internet|wi-?fi|ipad|tablet|"
                     r"m[oó]vil|switch|fire ?tv|consola|tele|tiktok|youtube|instagram|fortnite|roblox|twitch|netflix)\b")),
    Agente("seguridad", "Seguridad", "seguridad", "Informe defensivo de la red de casa (solo administradores).",
           "Eres el agente de Seguridad (Intel) de ARIA, solo para el administrador. Tu trabajo es DEFENSIVO y "
           f"se limita a la red de casa {config.RED_PERMITIDA}: escaneo de puertos con nmap, servicios de riesgo, "
           "dispositivos desconocidos, versiones con vulnerabilidades conocidas, dominios bloqueados por "
           "Pi-hole y peers de WireGuard sin uso. " + _COMUN +
           "Nunca ataques, explotes ni pruebes contraseñas, ni ayudes a hacerlo contra nada; si te lo piden, "
           "niégate y ofrece el informe defensivo. Prioriza los hallazgos por gravedad y da pasos concretos "
           "para corregirlos.",
           SEGURIDAD_TOOLS | _COMUNES | {"noticias", "dispositivos_red", "dispositivos_nuevos", "dispositivos_vpn",
                                         "estado_bloqueador"},
           roles=frozenset({"admin"}),
           palabras=(r"\bseguridad\b", r"\bescane\w*", r"\bnmap\b", r"\bpuertos?\b", r"\bvulnerab\w*", r"\bcve\b",
                     r"\bintrus\w*", r"\bhack\w*", r"\bataque\w*", r"\bamenaza\w*", r"\bmalware\b",
                     r"\bexpuest\w*", r"\bexposici[oó]n\b", r"\briesgos?\b", r"\binforme de seguridad\b")),
)}

_PREFIJO = re.compile(r"^\s*@(\w+)\b[\s,:]*", re.IGNORECASE)


def obtener(aid: str | None) -> Agente:
    return AGENTES.get(aid or AUTO, AGENTES[AUTO])


def permitido(aid: str, rol: str) -> bool:
    a = AGENTES.get(aid)
    return bool(a) and rol in a.roles


def disponibles(rol: str) -> list:
    return [a.publico() for a in AGENTES.values() if rol in a.roles]


def herramientas(agente: Agente, rol: str) -> set:
    """Herramientas del agente (más las de módulos que lo declaren) que además puede usar ese rol."""
    return (set(agente.herramientas) | tools.de_modulos(agente.id)) & tools.permitidas(rol)


def separar_prefijo(texto: str) -> tuple:
    """'@finanzas cuánto gasté' -> ('finanzas', 'cuánto gasté'). Un @ desconocido no se toca."""
    m = _PREFIJO.match(texto or "")
    if not m or m.group(1).lower() not in AGENTES:
        return None, texto
    resto = texto[m.end():].strip()
    return m.group(1).lower(), resto or texto


def puntuar(texto: str, rol: str) -> dict:
    """Coincidencias del filtro de palabras clave por agente especializado permitido al rol."""
    t = (texto or "").lower()
    out = {}
    for a in AGENTES.values():
        if a.id == AUTO or rol not in a.roles:
            continue
        n = sum(1 for p in a.palabras if re.search(p, t))
        if n:
            out[a.id] = n
    return out


async def pregunta_nube(sistema: str, texto: str, timeout: float = 8, maximo: int = 60) -> str | None:
    """Pregunta corta (sin herramientas) al primer cerebro en la nube disponible. None si no hay o falla."""
    prov = next((p for p in cerebros.cadena() if p.nube), None)
    if prov is None:
        return None
    salida = ""

    async def correr():
        nonlocal salida
        async for ev in prov.ronda([{"role": "user", "content": texto}], con_tools=False, sistema=sistema):
            if ev["type"] == "token":
                salida += ev["text"]
                if len(salida) > maximo:
                    break
    try:
        await asyncio.wait_for(correr(), timeout=timeout)
    except (cerebros.ProveedorError, asyncio.TimeoutError, TypeError):
        return None
    return salida


async def clasificar_con_nube(texto: str, candidatos: list) -> str | None:
    """Clasificación de una línea por el primer cerebro en la nube. Devuelve un id de `candidatos`, 'aria' o None."""
    opciones = ", ".join(f"{a} ({AGENTES[a].descripcion})" for a in candidatos)
    sistema = ("Eres un clasificador. Responde SOLO con una palabra: el identificador del agente que mejor "
               f"atiende el mensaje, o 'aria' si ninguno encaja. Opciones: {opciones}, aria (charla general).")
    salida = await pregunta_nube(sistema, texto[:500])
    for p in re.findall(r"[a-z]+", (salida or "").lower()):
        if p in candidatos or p == AUTO:
            return p
    return None


async def enrutar(texto: str, rol: str, clasificador=None) -> tuple:
    """Decide el agente para un mensaje en modo automático. Devuelve (id, motivo)."""
    puntos = puntuar(texto, rol)
    if not puntos:
        return AUTO, "general"
    mejor = max(puntos.values())
    empatados = sorted(a for a, n in puntos.items() if n == mejor)
    if len(puntos) == 1 or len(empatados) == 1 and mejor >= 2:
        return empatados[0], "palabras clave"
    elegido = await (clasificador or clasificar_con_nube)(texto, sorted(puntos))
    if elegido and elegido != AUTO and permitido(elegido, rol):
        return elegido, "clasificado por la nube"
    if elegido == AUTO:
        return AUTO, "clasificado por la nube"
    return (empatados[0], "palabras clave") if len(empatados) == 1 else (AUTO, "ambiguo")


def prompt(agente: Agente, nube: bool, nombre: str | None, admin: bool) -> str:
    if agente.id == AUTO:
        p = config.system_prompt(nube, nombre, admin)
        return p + (" Si te preguntan por finanzas, la red o la seguridad, el usuario puede escribir @finanzas, "
                    "@redes" + (" o @seguridad" if admin else "") + " para hablar con el especialista.")
    p = agente.prompt
    nombre = (config.NOMBRE_USUARIO if nombre is None else " ".join(str(nombre).split())[:40])
    if nombre:
        p += f" El usuario se llama {nombre}; trátale por su nombre cuando sea natural."
    if not admin:
        p += " Este usuario no es administrador: solo puede consultar; los cambios de la red los hace el administrador."
    if nube:
        n = datetime.now(ZoneInfo(config.TZ))
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        p += (f" Hoy es {dias[n.weekday()]} {n:%d/%m/%Y} ({n:%H:%M}); fíate de esta fecha, no de tu memoria."
              " Usa las herramientas solo cuando hagan falta de verdad para responder. Si el usuario te pide que "
              "recuerdes u olvides algo suyo, usa recordar y olvidar. Para avisos a una hora («recuérdame mañana a las 9…») usa recordatorio con la fecha ISO calculada. Si buscas en Internet, cita las fuentes como "
              "enlaces al final («Fuentes: [título](url)»).")
    return p
