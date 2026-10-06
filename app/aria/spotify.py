"""Cliente mínimo de la Web API de Spotify (flujo Authorization Code)."""
import json
import os
import secrets
import time
from urllib.parse import urlencode

import httpx

from . import config

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
TOKEN_FILE = config.DATA_DIR / "spotify_token.json"


class SpotifyError(Exception):
    """Error legible (en espanol) para mostrar al usuario o al modelo."""


def configured() -> bool:
    return bool(config.SPOTIFY_CLIENT_ID and config.SPOTIFY_CLIENT_SECRET)


def new_state() -> str:
    return secrets.token_urlsafe(16)


def auth_url(state: str) -> str:
    q = {
        "client_id": config.SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": config.SPOTIFY_REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(q)}"


def _load() -> dict | None:
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (OSError, ValueError):
        return None


def _save(tok: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(tok, f)
    os.replace(tmp, TOKEN_FILE)


def connected() -> bool:
    return bool(_load())


async def _token_request(data: dict) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(TOKEN_URL, data=data, auth=(config.SPOTIFY_CLIENT_ID, config.SPOTIFY_CLIENT_SECRET))
    if r.status_code != 200:
        raise SpotifyError("Spotify rechazó la autorización. Vuelve a conectar la cuenta.")
    return r.json()


async def exchange_code(code: str) -> None:
    j = await _token_request(
        {"grant_type": "authorization_code", "code": code, "redirect_uri": config.SPOTIFY_REDIRECT_URI}
    )
    _save({
        "access_token": j["access_token"],
        "refresh_token": j.get("refresh_token", ""),
        "expires_at": time.time() + j.get("expires_in", 3600) - 30,
    })


async def _access_token() -> str:
    if not configured():
        raise SpotifyError("Spotify no está configurado. El administrador debe añadir SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET al archivo .env de la Raspberry Pi (ver README). Nunca compartas esas claves en el chat.")
    tok = _load()
    if not tok:
        raise SpotifyError("Spotify no está conectado. Pulsa 'Conectar Spotify' en el panel.")
    if time.time() >= tok["expires_at"]:
        j = await _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
        tok["access_token"] = j["access_token"]
        tok["refresh_token"] = j.get("refresh_token", tok["refresh_token"])
        tok["expires_at"] = time.time() + j.get("expires_in", 3600) - 30
        _save(tok)
    return tok["access_token"]


async def _call(method: str, path: str, **kw) -> httpx.Response:
    token = await _access_token()
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.request(method, API + path, headers={"Authorization": f"Bearer {token}"}, **kw)
    if r.status_code == 404 and "NO_ACTIVE_DEVICE" in r.text:
        raise SpotifyError("No hay ningún dispositivo de Spotify activo. Abre Spotify en un móvil u ordenador y reintenta.")
    if r.status_code == 403:
        raise SpotifyError("Spotify denegó la acción (el control de reproducción requiere cuenta Premium).")
    if r.status_code == 401:
        raise SpotifyError("La sesión de Spotify ha caducado. Vuelve a conectar la cuenta.")
    if r.status_code == 429:
        raise SpotifyError("Spotify limito las peticiones. Espera unos segundos.")
    if r.status_code >= 400:
        raise SpotifyError(f"Spotify devolvió un error ({r.status_code}).")
    return r


async def play() -> str:
    await _call("PUT", "/me/player/play")
    return "Reproducción reanudada."


async def pause() -> str:
    await _call("PUT", "/me/player/pause")
    return "Reproducción en pausa."


async def next_track() -> str:
    await _call("POST", "/me/player/next")
    return "Pasando a la siguiente canción."


async def previous_track() -> str:
    await _call("POST", "/me/player/previous")
    return "Volviendo a la canción anterior."


async def current() -> dict:
    r = await _call("GET", "/me/player/currently-playing")
    if r.status_code == 204 or not r.content:
        return {"reproduciendo": False}
    j = r.json()
    item = j.get("item") or {}
    return {
        "reproduciendo": bool(j.get("is_playing")),
        "titulo": item.get("name"),
        "artistas": ", ".join(a["name"] for a in item.get("artists", [])),
        "album": (item.get("album") or {}).get("name"),
    }


async def search_and_play(query: str) -> str:
    r = await _call("GET", "/search", params={"q": query, "type": "track", "limit": 1})
    items = r.json().get("tracks", {}).get("items", [])
    if not items:
        return f"No he encontrado nada en Spotify para '{query}'."
    t = items[0]
    await _call("PUT", "/me/player/play", json={"uris": [t["uri"]]})
    artistas = ", ".join(a["name"] for a in t["artists"])
    return f"Reproduciendo '{t['name']}' de {artistas}."
