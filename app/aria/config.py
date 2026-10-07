"""Configuracion de ARIA leida del entorno (.env)."""
import os
from datetime import datetime
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


NOMBRE_USUARIO = os.environ.get("ARIA_NOMBRE_USUARIO", "").strip()[:40]

_PROMPT_BASE = (
    "Eres ARIA, un asistente doméstico útil que corre en local en una Raspberry Pi. "
    "Responde siempre en español de España, de forma breve y clara. "
    "Usa las herramientas disponibles solo cuando el usuario pida datos en vivo: la hora, el estado "
    "de los servicios, el bloqueador de anuncios, los dispositivos VPN, el estado de la Raspberry Pi, "
    "controlar Spotify, buscar algo en Netflix o buscar información y noticias en internet; no inventes sus resultados. "
    "Si te piden explicar un concepto o charlar, responde sin herramientas. "
    "Recuerda que no puedes reproducir contenido de Netflix: solo puedes dar un enlace de búsqueda."
)


_PROMPT_LECTURA = (
    "Eres ARIA, un asistente doméstico útil que corre en local en una Raspberry Pi. "
    "Responde siempre en español de España, de forma breve y clara. "
    "Usa las herramientas disponibles solo cuando el usuario pida datos en vivo: la hora, el estado "
    "de los servicios, el bloqueador de anuncios, los dispositivos VPN, el estado de la Raspberry Pi, "
    "buscar algo en Netflix o buscar información y noticias en internet; no inventes sus resultados. Solo puedes consultar datos: no puedes "
    "pausar el bloqueador, cambiar la VPN ni controlar Spotify; si te lo piden, explica que eso "
    "lo hace el administrador. "
    "Si te piden explicar un concepto o charlar, responde sin herramientas. "
    "Recuerda que no puedes reproducir contenido de Netflix: solo puedes dar un enlace de búsqueda."
)


def system_prompt(nube: bool = False, nombre: str | None = None, admin: bool = True) -> str:
    """Prompt del sistema. Los cerebros en la nube reciben todas las herramientas y una línea extra.

    `nombre` es el nombre del usuario que chatea (None = el global ARIA_NOMBRE_USUARIO)."""
    p = _PROMPT_BASE if admin else _PROMPT_LECTURA
    nombre = (NOMBRE_USUARIO if nombre is None else " ".join(str(nombre).split())[:40])
    if nombre:
        p += f" El usuario se llama {nombre}; trátale por su nombre cuando sea natural."
    if nube:
        n = datetime.now(ZoneInfo(TZ))
        p += f" Hoy es {n:%d/%m/%Y} ({n:%H:%M}, {TZ}); fíate de esta fecha, no de tu memoria."
        p += (" Tienes herramientas a tu disposición, pero úsalas solo cuando hagan falta de verdad "
              "para responder; si la pregunta no necesita datos en vivo, contesta directamente. "
              "Para cualquier cosa reciente o factual de la que no estés seguro (noticias, precios, resultados, "
              "datos de lugares o personas) usa buscar_en_internet o noticias, y cita las fuentes como enlaces "
              "al final de la respuesta con el formato «Fuentes: [título](url), ...».")
    return p


SYSTEM_PROMPT = system_prompt(False)
