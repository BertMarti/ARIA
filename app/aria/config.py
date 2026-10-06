"""Configuracion de ARIA leida del entorno (.env)."""
import os
from pathlib import Path


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
MODEL = os.environ.get("ARIA_MODEL", "llama3.2:3b")
NUM_CTX = _int("ARIA_NUM_CTX", 4096)
KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "5m")
TZ = os.environ.get("ARIA_TZ", "Europe/Madrid")

SHIELD_DNS_HOST = os.environ.get("SHIELD_DNS_HOST", "host.docker.internal")
SHIELD_DNS_PORT = _int("SHIELD_DNS_PORT", 53)
SHIELD_WEB_PORT = _int("SHIELD_WEB_PORT", 8443)
HEIMDALL_HOST = os.environ.get("HEIMDALL_HOST", "host.docker.internal")
HEIMDALL_PORT = _int("HEIMDALL_PORT", 51843)

SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI") or f"https://{LAN_IP}/spotify/callback"

DATA_DIR = Path(os.environ.get("ARIA_DATA_DIR", "/data"))
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

SYSTEM_PROMPT = (
    "Eres ARIA, un asistente doméstico útil que corre en local en una Raspberry Pi. "
    "Responde siempre en español de España, de forma breve y clara. "
    "Usa las herramientas disponibles cuando el usuario pida la hora, el estado de los "
    "servicios, controlar Spotify o buscar algo en Netflix; no inventes sus resultados. "
    "Recuerda que no puedes reproducir contenido de Netflix: solo puedes dar un enlace de búsqueda."
)
