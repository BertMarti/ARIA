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


SYSTEM_PROMPT = (
    "Eres ARIA, un asistente doméstico útil que corre en local en una Raspberry Pi. "
    "Responde siempre en español de España, de forma breve y clara. "
    "Usa las herramientas disponibles solo cuando el usuario pida datos en vivo: la hora, el estado "
    "de los servicios, el bloqueador de anuncios, los dispositivos VPN, el estado de la Raspberry Pi, "
    "controlar Spotify o buscar algo en Netflix; no inventes sus resultados. "
    "Si te piden explicar un concepto o charlar, responde sin herramientas. "
    "Recuerda que no puedes reproducir contenido de Netflix: solo puedes dar un enlace de búsqueda."
)
