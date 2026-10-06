"""Herramientas que el modelo puede invocar (tool calling de Ollama).

Para anadir una herramienta nueva basta con decorar una funcion con @tool:

    @tool("mi_herramienta", "Que hace (en espanol)", {"param": ("string", "descripcion")})
    async def mi_herramienta(param: str) -> str:
        return "resultado"

Debe devolver un str o algo serializable a JSON. Los errores se capturan en
ejecutar() y se devuelven al modelo como texto.
"""
import json
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from . import config, services, spotify

_REGISTRO: dict = {}

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def tool(nombre: str, descripcion: str, params: dict | None = None, requeridos: tuple = ()):
    def deco(fn):
        props = {k: {"type": t, "description": d} for k, (t, d) in (params or {}).items()}
        _REGISTRO[nombre] = {
            "fn": fn,
            "spec": {
                "type": "function",
                "function": {
                    "name": nombre,
                    "description": descripcion,
                    "parameters": {"type": "object", "properties": props, "required": list(requeridos)},
                },
            },
        }
        return fn
    return deco


def especificaciones() -> list:
    return [t["spec"] for t in _REGISTRO.values()]


async def ejecutar(nombre: str, args: dict | None) -> str:
    t = _REGISTRO.get(nombre)
    if not t:
        return f"Herramienta desconocida: {nombre}"
    try:
        res = await t["fn"](**(args or {}))
    except spotify.SpotifyError as e:
        return str(e)
    except TypeError:
        return "Argumentos no validos para la herramienta."
    except Exception as e:  # noqa: BLE001 - se informa al modelo, no se rompe el chat
        return f"Error al ejecutar la herramienta: {type(e).__name__}"
    return res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)


@tool("fecha_hora", "Devuelve la fecha y hora actuales.")
async def fecha_hora() -> str:
    n = datetime.now(ZoneInfo(config.TZ))
    return f"{DIAS[n.weekday()]}, {n.day} de {MESES[n.month - 1]} de {n.year}, {n:%H:%M} ({config.TZ})"


@tool("estado_servicios", "Consulta el estado de los servicios SHIELD-DNS (bloqueo de anuncios) y HEIMDALL (VPN).")
async def estado_servicios() -> dict:
    return await services.estado()


@tool("spotify_play", "Reanuda la reproduccion en Spotify.")
async def spotify_play() -> str:
    return await spotify.play()


@tool("spotify_pause", "Pausa la reproduccion en Spotify.")
async def spotify_pause() -> str:
    return await spotify.pause()


@tool("spotify_siguiente", "Salta a la siguiente cancion en Spotify.")
async def spotify_siguiente() -> str:
    return await spotify.next_track()


@tool("spotify_anterior", "Vuelve a la cancion anterior en Spotify.")
async def spotify_anterior() -> str:
    return await spotify.previous_track()


@tool("spotify_actual", "Dice que cancion suena ahora mismo en Spotify.")
async def spotify_actual() -> dict:
    return await spotify.current()


@tool("spotify_buscar_y_reproducir", "Busca una cancion o artista en Spotify y la reproduce.",
      {"consulta": ("string", "Cancion y/o artista a buscar")}, ("consulta",))
async def spotify_buscar_y_reproducir(consulta: str) -> str:
    return await spotify.search_and_play(str(consulta))


@tool("buscar_en_netflix",
      "Genera un enlace de busqueda en Netflix. No puede reproducir nada: solo devuelve el enlace para abrirlo.",
      {"titulo": ("string", "Titulo de la serie o pelicula")}, ("titulo",))
async def buscar_en_netflix(titulo: str) -> str:
    return f"https://www.netflix.com/search?q={quote(str(titulo))} (ARIA no puede controlar Netflix; abre el enlace para buscarlo)"
