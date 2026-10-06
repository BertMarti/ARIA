"""Herramientas que el modelo puede invocar (tool calling de Ollama).

Para anadir una herramienta nueva basta con decorar una funcion con @tool:

    @tool("mi_herramienta", "Que hace (en espanol)", {"param": ("string", "descripcion")})
    async def mi_herramienta(param: str) -> str:
        return "resultado"

Debe devolver un str o algo serializable a JSON. Los errores se capturan en
ejecutar() y se devuelven al modelo como texto.
"""
import json
import re
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from . import config, services, spotify

_REGISTRO: dict = {}

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
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


def especificaciones(nombres=None) -> list:
    return [t["spec"] for n, t in _REGISTRO.items() if nombres is None or n in nombres]


# Los modelos pequenos (3B) llaman herramientas sin motivo si se les ofrecen todas.
# Solo se ofrecen las relacionadas con lo que pide el usuario (palabras clave).
_INTENCIONES = [
    # (patrones que deben cumplirse TODOS, herramientas que se ofrecen)
    ((r"\b(hora|horas|fecha|d[ií]a|hoy|ma[nñ]ana|semana|mes)\b",), {"fecha_hora"}),
    ((r"\b(servicios?|vpn|heimdall|shield|dns|bloqueador|anuncios?|publicidad)\b",
      r"\b(funciona\w*|estado|activ[oa]s?|ca[ií]d[oa]s?|encendid[oa]s?|apagad[oa]s?|est[aá]n?|va|van)\b"),
     {"estado_servicios"}),
    ((r"\b(spotify|m[uú]sica|canci[oó]n|canciones|pon|ponme|reproduce|pausa|para la|siguiente|anterior|suena|sonando|artista|disco|[aá]lbum)\b",),
     {"spotify_play", "spotify_pause", "spotify_siguiente", "spotify_anterior", "spotify_actual",
      "spotify_buscar_y_reproducir"}),
    ((r"\b(netflix|serie|series|pel[ií]cula|pel[ií]culas|cap[ií]tulo)\b",), {"buscar_en_netflix"}),
]


def relevantes(texto: str) -> set:
    t = texto.lower()
    out = set()
    for patrones, nombres in _INTENCIONES:
        if all(re.search(p, t) for p in patrones):
            out |= nombres
    return out


def rescatar_llamada(texto: str, permitidas: set) -> dict | None:
    """Los modelos pequenos a veces escriben la llamada como JSON en el texto
    (a menudo mal formado). Si se reconoce una herramienta permitida y sus
    argumentos obligatorios, se convierte en una llamada real."""
    for nombre in sorted(permitidas, key=len, reverse=True):
        if nombre not in texto:
            continue
        params = _REGISTRO[nombre]["spec"]["function"]["parameters"]
        args = {}
        for p in params["properties"]:
            m = re.search(r'"%s"\s*:\s*\\?"((?:\\u[0-9a-fA-F]{4}|[^"\\])+)' % re.escape(p), texto)
            if m:
                args[p] = re.sub(r"\\u([0-9a-fA-F]{4})", lambda x: chr(int(x.group(1), 16)), m.group(1))
        if all(r in args for r in params["required"]):
            return {"function": {"name": nombre, "arguments": args}}
    return None


async def ejecutar(nombre: str, args: dict | None) -> str:
    t = _REGISTRO.get(nombre)
    if not t:
        return f"Herramienta desconocida: {nombre}"
    try:
        res = await t["fn"](**(args or {}))
    except spotify.SpotifyError as e:
        return str(e)
    except TypeError:
        return "Argumentos no válidos para la herramienta."
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


@tool("spotify_play", "Reanuda la reproducción en Spotify.")
async def spotify_play() -> str:
    return await spotify.play()


@tool("spotify_pause", "Pausa la reproducción en Spotify.")
async def spotify_pause() -> str:
    return await spotify.pause()


@tool("spotify_siguiente", "Salta a la siguiente canción en Spotify.")
async def spotify_siguiente() -> str:
    return await spotify.next_track()


@tool("spotify_anterior", "Vuelve a la canción anterior en Spotify.")
async def spotify_anterior() -> str:
    return await spotify.previous_track()


@tool("spotify_actual", "Dice que canción suena ahora mismo en Spotify.")
async def spotify_actual() -> dict:
    return await spotify.current()


@tool("spotify_buscar_y_reproducir", "Busca una canción o artista en Spotify y la reproduce.",
      {"consulta": ("string", "Canción y/o artista a buscar")}, ("consulta",))
async def spotify_buscar_y_reproducir(consulta: str) -> str:
    return await spotify.search_and_play(str(consulta))


@tool("buscar_en_netflix",
      "Genera un enlace de búsqueda en Netflix. No puede reproducir nada: solo devuelve el enlace para abrirlo.",
      {"titulo": ("string", "Título de la serie o película")}, ("titulo",))
async def buscar_en_netflix(titulo: str) -> str:
    return f"https://www.netflix.com/search?q={quote(str(titulo))} (ARIA no puede controlar Netflix; abre el enlace para buscarlo)"
