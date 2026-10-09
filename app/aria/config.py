"""Configuracion de ARIA leida del entorno (.env)."""
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


USER = os.environ.get("ARIA_USER", "")
PASSWORD = os.environ.get("ARIA_PASSWORD", "")
SECRET = os.environ.get("ARIA_SECRET", "")

LAN_IP = os.environ.get("ARIA_LAN_IP", "127.0.0.1")
HOSTS = {h.strip().lower() for h in os.environ.get("ARIA_HOSTS", "").split(",") if h.strip()}
HOSTS.add(LAN_IP.lower())

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
VERSION = "2.0.0"
MODEL_POR_DEFECTO = os.environ.get("ARIA_MODEL", "llama3.2:3b")
NUM_CTX = _int("ARIA_NUM_CTX", 4096)
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "5m")
TZ = os.environ.get("ARIA_TZ", "Europe/Madrid")

SHIELD_DNS_HOST = os.environ.get("SHIELD_DNS_HOST", "host.docker.internal")
SHIELD_DNS_PORT = _int("SHIELD_DNS_PORT", 53)
SHIELD_WEB_PORT = _int("SHIELD_WEB_PORT", 8443)
HEIMDALL_HOST = os.environ.get("HEIMDALL_HOST", "host.docker.internal")
HEIMDALL_PORT = _int("HEIMDALL_PORT", 51843)

# Integraciones del laboratorio (opcionales). Vacías = "no conectado".
SHIELD_URL = os.environ.get("SHIELD_URL") or f"http://{LAN_IP}:8080"
SHIELD_PASSWORD = os.environ.get("SHIELD_PASSWORD", "")
VPN_URL = os.environ.get("VPN_URL") or f"https://{LAN_IP}:51843"
VPN_USER = os.environ.get("VPN_USER", "")
VPN_PASSWORD = os.environ.get("VPN_PASSWORD", "")

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI") or f"https://{LAN_IP}/spotify/callback"

# Inicio de sesión único con Cloudflare Access (vacío = desactivado).
CF_TEAM = os.environ.get("ARIA_CF_ACCESS_TEAM", "").strip().lower().removeprefix("https://").strip("/")
CF_AUD = os.environ.get("ARIA_CF_ACCESS_AUD", "").strip()
ADMIN_EMAILS = [e.strip().lower() for e in os.environ.get("ARIA_ADMIN_EMAILS", "").split(",") if e.strip()]

# Agentes Redes / Seguridad. La red permitida es la ÚNICA que se puede escanear (guardia en la app y en el escáner).
RED_PERMITIDA = (os.environ.get("ARIA_RED_PERMITIDA") or "192.168.0.0/24").strip()
ROUTER_IP = (os.environ.get("ARIA_ROUTER_IP") or "192.168.0.1").strip()
# Control parental (control.py): ARIA_CONTROL=0 lo desactiva. IPs que NUNCA se pueden pausar ni bloquear (además
# del router, la Raspberry y ARIA_LAN_IP), separadas por comas.
CONTROL = os.environ.get("ARIA_CONTROL", "1").strip().lower() not in ("0", "false", "no", "off")
CONTROL_PROTEGIDOS = {i.strip() for i in os.environ.get("ARIA_CONTROL_PROTEGIDOS", "").split(",") if i.strip()}
ESCANER_DIR = Path(os.environ.get("ARIA_ESCANER_DIR", "/escaner"))
SPEEDTEST_URL = os.environ.get("ARIA_SPEEDTEST_URL", "https://speed.cloudflare.com").rstrip("/")

def _url_publica() -> str:
    """URL pública de ARIA (túnel de Cloudflare): ARIA_URL_PUBLICA o el primer dominio de ARIA_HOSTS
    que no sea una IP ni .local/.lan. Vacía = no hay acceso desde fuera (el chequeo del túnel se omite)."""
    u = os.environ.get("ARIA_URL_PUBLICA", "").strip().rstrip("/")
    if u:
        return u if u.startswith("https://") else ""
    for h in sorted(HOSTS):
        if "." in h and not h.replace(".", "").isdigit() and not h.endswith((".local", ".lan", ".localhost")) and ":" not in h:
            return f"https://{h}"
    return ""


URL_PUBLICA = _url_publica()

# Avisos: Telegram (bot con long polling, sin webhook) y notificaciones push (Web Push con VAPID).
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "").strip() or "mailto:admin@aria.invalid"
DATA_DIR = Path(os.environ.get("ARIA_DATA_DIR", "/data"))
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

MODEL_FILE = DATA_DIR / "model.txt"


def modelo_activo() -> str:
    """Modelo elegido en Ajustes (data/model.txt); si no existe, ARIA_MODEL."""
    try:
        m = MODEL_FILE.read_text().strip()
        if m:
            return m
    except OSError:
        pass
    return MODEL_POR_DEFECTO


def guardar_modelo(nombre: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_FILE.write_text(nombre.strip() + "\n")


# Resumen de buenos días: ciudad para el tiempo (Open-Meteo, sin clave). Vacío = sin tiempo.
CIUDAD = os.environ.get("ARIA_CIUDAD", "").strip()[:80]
# Opcional: coordenadas fijas (evitan geocodificar). Ambas deben estar rellenas.
def _float(name: str):
    try:
        return float(os.environ.get(name, "").replace(",", "."))
    except ValueError:
        return None


LAT, LON = _float("ARIA_LAT"), _float("ARIA_LON")
# Repositorio de copias fuera de la Pi (solo se lee si está montado en el contenedor).
COPIAS_REPO = os.environ.get("ARIA_COPIAS_REPO", "/copias-repo")

NOMBRE_USUARIO = os.environ.get("ARIA_NOMBRE_USUARIO", "").strip()[:40]

# Funciones aparcadas hasta más adelante (8/10/2026): el código sigue, pero sin herramientas
# ni interfaz salvo que se activen en .env con ARIA_SPOTIFY=1 / ARIA_NETFLIX=1.
SPOTIFY = os.environ.get("ARIA_SPOTIFY", "0") == "1"
NETFLIX = os.environ.get("ARIA_NETFLIX", "0") == "1"
# Precio de la luz (PVPC de España, API pública de Red Eléctrica). ARIA_LUZ=0 lo apaga fuera de España.
LUZ = os.environ.get("ARIA_LUZ", "1") != "0"
_EXTRAS = "".join(", " + x for x, si in (("controlar Spotify", SPOTIFY), ("buscar algo en Netflix", NETFLIX)) if si)
_NOTA_NETFLIX = " Recuerda que no puedes reproducir contenido de Netflix: solo puedes dar un enlace de búsqueda." if NETFLIX else ""

_PROMPT_BASE = (
    "Eres ARIA, un asistente doméstico útil que corre en local en una Raspberry Pi. "
    "Responde siempre en español de España, de forma breve y clara. "
    "Usa las herramientas disponibles solo cuando el usuario pida datos en vivo: la hora, el estado "
    "de los servicios, el bloqueador de anuncios, los dispositivos VPN, el estado de la Raspberry Pi"
    f"{_EXTRAS} o buscar información y noticias en internet; no inventes sus resultados. "
    "Si te piden explicar un concepto o charlar, responde sin herramientas."
    + _NOTA_NETFLIX
)


_PROMPT_LECTURA = (
    "Eres ARIA, un asistente doméstico útil que corre en local en una Raspberry Pi. "
    "Responde siempre en español de España, de forma breve y clara. "
    "Usa las herramientas disponibles solo cuando el usuario pida datos en vivo: la hora, el estado "
    "de los servicios, el bloqueador de anuncios, los dispositivos VPN, el estado de la Raspberry Pi"
    + (", buscar algo en Netflix" if NETFLIX else "")
    + " o buscar información y noticias en internet; no inventes sus resultados. Solo puedes consultar datos: no puedes "
    + ("pausar el bloqueador, cambiar la VPN ni controlar Spotify; " if SPOTIFY else "pausar el bloqueador ni cambiar la VPN; ")
    + "si te lo piden, explica que eso lo hace el administrador. "
    "Si te piden explicar un concepto o charlar, responde sin herramientas."
    + _NOTA_NETFLIX
)


def system_prompt(nube: bool = False, nombre: str | None = None, admin: bool = True, extra: str = "") -> str:
    """Prompt del sistema. Los cerebros en la nube reciben todas las herramientas y una línea extra.

    `nombre` es el nombre del usuario que chatea (None = el global ARIA_NOMBRE_USUARIO)."""
    p = _PROMPT_BASE if admin else _PROMPT_LECTURA
    nombre = (NOMBRE_USUARIO if nombre is None else " ".join(str(nombre).split())[:40])
    if nombre:
        p += f" El usuario se llama {nombre}; trátale por su nombre cuando sea natural."
    if nube:
        n = datetime.now(ZoneInfo(TZ))
        dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        sab = n + timedelta(days=(5 - n.weekday()) % 7)
        p += (f" Hoy es {dias[n.weekday()]} {n:%d/%m/%Y} ({n:%H:%M}, {TZ}); fíate de esta fecha, no de tu memoria."
              f" Este fin de semana es el sábado {sab:%d/%m} y el domingo {sab + timedelta(days=1):%d/%m}.")
        p += (" Tienes herramientas a tu disposición, pero úsalas solo cuando hagan falta de verdad "
              "para responder; si la pregunta no necesita datos en vivo, contesta directamente. "
              "Si el usuario te pide que recuerdes u olvides algo suyo, usa las herramientas recordar y olvidar. "
              "Si te pide que le avises o le recuerdes algo en un momento concreto («recuérdame mañana a las 9…», "
              "«avísame en 20 minutos», «todos los lunes a las 8…»), usa la herramienta recordatorio con la fecha y "
              "hora ISO que calcules a partir de la de hoy (recordar es solo para datos permanentes). "
              "Si quiere que hagas algo tú solo de forma periódica («cada mañana a las 8 dime el tiempo», «crea una "
              "rutina…»), usa crear_rutina (un recordatorio solo le avisa con un texto fijo). "
              "Si pega o comparte un enlace y pide un resumen o tu opinión, usa resumir_enlace. "
              "Para cualquier cosa reciente o factual de la que no estés seguro (noticias, precios, resultados, "
              "datos de lugares o personas) usa buscar_en_internet o noticias, y cita las fuentes como enlaces "
              "al final de la respuesta con el formato «Fuentes: [título](url), ...».")
    if extra:
        p += "\n\n" + extra
    return p


SYSTEM_PROMPT = system_prompt(False)
