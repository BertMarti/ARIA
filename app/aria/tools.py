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

from . import config, services, shield, sistema, spotify, vpn

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


# Herramientas que puede usar un usuario sin rol de administrador (solo consultan).
SOLO_LECTURA = frozenset({"fecha_hora", "estado_servicios", "estado_bloqueador", "dispositivos_vpn",
                          "estado_sistema", "buscar_en_netflix"})


def permitidas(rol: str) -> set:
    """Nombres de herramientas que ese rol puede ver y ejecutar."""
    return set(_REGISTRO) if rol == "admin" else set(SOLO_LECTURA) & set(_REGISTRO)


def especificaciones(nombres=None) -> list:
    return [t["spec"] for n, t in _REGISTRO.items() if nombres is None or n in nombres]


# Los modelos pequenos (3B) llaman herramientas sin motivo si se les ofrecen todas.
# Solo se ofrecen las relacionadas con lo que pide el usuario (palabras clave).
# Un patron que empieza por "!" debe NO aparecer en el mensaje.
_BLOQUEADOR = r"\b(bloqueador|anuncios?|publicidad|pi-?hole|shield|adblock|ads)\b"
_SISTEMA = (r"\b(raspberry|rasp|ram|cpu|uptime|procesador|servidor|temperatura|memoria|disco|"
            r"almacenamiento|espacio|sistema)\b")
_EXPLICAR = r"!\b(expl[ií]ca\w*|qu[eé] es|qu[eé] significa|para qu[eé] sirve)\b"  # preguntas conceptuales
_INTENCIONES = [
    # (patrones que deben cumplirse TODOS, herramientas que se ofrecen)
    ((r"\b(hora|horas|fecha|d[ií]a|hoy|ma[nñ]ana|semana|mes)\b",
      r"!" + _BLOQUEADOR, r"!" + _SISTEMA, r"!\b(vpn|wireguard|heimdall)\b"), {"fecha_hora"}),
    ((r"\b(servicios?|vpn|heimdall|shield|dns|bloqueador|anuncios?|publicidad)\b",
      r"\b(funciona\w*|estado|activ[oa]s?|ca[ií]d[oa]s?|encendid[oa]s?|apagad[oa]s?|est[aá]n?|va|van)\b"),
     {"estado_servicios"}),
    ((_BLOQUEADOR,
      r"\b(cu[aá]nt\w+|estad[ií]stic\w*|estado|funciona\w*|bloquead[oa]s?|resumen|porcentaje|consultas|n[uú]meros)\b"),
     {"estado_bloqueador"}),
    ((_BLOQUEADOR, r"\b(paus\w+|desactiv\w+|apag\w+|det[eé]n\w*|desconect\w+)\b"), {"pausar_bloqueador"}),
    ((_BLOQUEADOR, r"\b(reanud\w+|activ[ae]\w*|reactiv\w+|enciend\w+|encend\w+|conect[ae]\w*|vuelve\w*|contin[uú]\w+)\b"),
     {"reanudar_bloqueador"}),
    ((r"\b(vpn|wireguard|heimdall)\b",
      r"\b(dispositivos?|conectad\w+|clientes?|cu[aá]nt\w+|hay|lista\w*|m[oó]viles?|tel[eé]fonos?|qui[eé]n\w*)\b"),
     {"dispositivos_vpn"}),
    ((r"\b(vpn|wireguard|heimdall)\b",
      r"\b(a[ñn]ad\w*|cre[ao]\w*|nuev[oa]s?|agreg\w+|dar de alta|alta)\b", _EXPLICAR), {"crear_dispositivo_vpn"}),
    ((r"\b(vpn|wireguard|heimdall|dispositivos?)\b",
      r"\b(activa|activar|act[ií]valo|desactiva|desactivar|desact[ií]valo|habilita|deshabilita|apaga|apagar|enciende|encender)\b",
      _EXPLICAR), {"activar_dispositivo_vpn", "desactivar_dispositivo_vpn", "dispositivos_vpn"}),
    ((r"\b(raspberry|rasp|uptime|procesador)\b", _EXPLICAR), {"estado_sistema"}),
    ((r"\b(temperatura|memoria|ram|cpu|disco|almacenamiento|espacio|sistema)\b",
      r"\b(libre|libres|queda\w*|usad\w+|ocupad\w+|tiene|estado|c[oó]mo|cu[aá]nt\w+|qu[eé])\b", _EXPLICAR),
     {"estado_sistema"}),
    ((r"\b(spotify|m[uú]sica|canci[oó]n|canciones|pon|ponme|reproduce|pausa|para la|siguiente|anterior|suena|sonando|artista|disco|[aá]lbum)\b",
      r"!" + _BLOQUEADOR, r"!\b(raspberry|ram|cpu|espacio|libre|temperatura)\b"),
     {"spotify_play", "spotify_pause", "spotify_siguiente", "spotify_anterior", "spotify_actual",
      "spotify_buscar_y_reproducir"}),
    ((r"\b(netflix|serie|series|pel[ií]cula|pel[ií]culas|cap[ií]tulo)\b",), {"buscar_en_netflix"}),
]


def relevantes(texto: str) -> set:
    t = texto.lower()
    out = set()
    for patrones, nombres in _INTENCIONES:
        if all((not re.search(p[1:], t)) if p.startswith("!") else re.search(p, t) for p in patrones):
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
            m = re.search(r'"%s"\s*:\s*(?:\\?"((?:\\u[0-9a-fA-F]{4}|[^"\\])+)|(-?\d+(?:\.\d+)?))' % re.escape(p), texto)
            if m:
                if m.group(1) is not None:
                    args[p] = re.sub(r"\\u([0-9a-fA-F]{4})", lambda x: chr(int(x.group(1), 16)), m.group(1))
                else:
                    args[p] = m.group(2)
        if all(r in args for r in params["required"]):
            return {"function": {"name": nombre, "arguments": args}}
    return None


async def ejecutar(nombre: str, args: dict | None, rol: str = "admin") -> str:
    t = _REGISTRO.get(nombre)
    if not t:
        return f"Herramienta desconocida: {nombre}"
    if nombre not in permitidas(rol):
        return "No tienes permiso para esa acción: pídesela al administrador."
    try:
        res = await t["fn"](**(args or {}))
    except (spotify.SpotifyError, shield.ShieldError, vpn.VpnError) as e:
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


@tool("estado_bloqueador",
      "Estadísticas del bloqueador de anuncios SHIELD-DNS (Pi-hole): consultas DNS, bloqueadas y porcentaje en las últimas 24 horas.")
async def estado_bloqueador() -> str:
    r = await shield.resumen()
    estado = "activo" if r["bloqueo_activo"] else "en pausa"
    return (f"Bloqueador {estado}. Últimas 24 h: {r['consultas']} consultas, {r['bloqueadas']} bloqueadas "
            f"({r['porcentaje']} %). Dominios en la lista de bloqueo: {r['lista_negra']}.")


@tool("pausar_bloqueador", "Pausa temporalmente el bloqueador de anuncios (entre 1 y 120 minutos).",
      {"minutos": ("integer", "Minutos de pausa, de 1 a 120")})
async def pausar_bloqueador(minutos=5) -> str:
    try:
        n = int(float(minutos))
    except (TypeError, ValueError):
        return "Indica la duración de la pausa en minutos (entre 1 y 120)."
    if not 1 <= n <= 120:
        return "La pausa debe durar entre 1 y 120 minutos."
    await shield.pausar(n)
    return f"Bloqueador de anuncios en pausa durante {n} minutos."


@tool("reanudar_bloqueador", "Reactiva el bloqueador de anuncios si estaba en pausa.")
async def reanudar_bloqueador() -> str:
    await shield.reanudar()
    return "Bloqueador de anuncios reactivado."


@tool("dispositivos_vpn",
      "Lista los dispositivos de la VPN HEIMDALL y cuáles están conectados ahora (handshake de menos de 3 minutos).")
async def dispositivos_vpn() -> str:
    cl = await vpn.listar()
    if not cl:
        return "La VPN está activa pero la lista de dispositivos está vacía: no hay ningún dispositivo registrado."
    partes = [f"{c['nombre']} ({'conectado' if c['conectado'] else 'desconectado'}"
              f"{'' if c['activo'] else ', desactivado'})" for c in cl]
    return f"{len(cl)} dispositivo(s): " + ", ".join(partes) + f". Conectados ahora: {sum(c['conectado'] for c in cl)}."


@tool("estado_sistema", "Estado de la Raspberry Pi: temperatura de la CPU, memoria RAM, disco, carga y tiempo encendida.")
async def estado_sistema() -> str:
    e = sistema.estado()
    gb = lambda b: f"{b / 1024 ** 3:.1f} GB"  # noqa: E731
    out = []
    if e["temperatura"] is not None:
        out.append(f"Temperatura de la CPU: {e['temperatura']} °C")
    if e["memoria"]:
        m = e["memoria"]
        out.append(f"RAM: {gb(m['usada'])} usados de {gb(m['total'])} ({m['porcentaje']} % ocupada)")
    if e["disco"]:
        d = e["disco"]
        out.append(f"Disco: {gb(d['usado'])} usados de {gb(d['total'])} ({d['porcentaje']} % ocupado), {gb(d['libre'])} libres")
    if e["carga"]:
        out.append("Carga media: " + " / ".join(f"{x:.2f}" for x in e["carga"]))
    out.append(f"Encendida desde hace {e['uptime_texto']}")
    return ". ".join(out) + "."


@tool("crear_dispositivo_vpn",
      "Crea un dispositivo nuevo (móvil, portátil...) en la VPN HEIMDALL. No devuelve claves: el usuario escanea el QR en la web.",
      {"nombre": ("string", "Nombre del dispositivo (letras sin tilde, números, espacios y - _ .; máximo 32)")}, ("nombre",))
async def crear_dispositivo_vpn(nombre: str) -> str:
    nombre = str(nombre).strip()
    if not vpn.nombre_valido(nombre):
        return "Nombre no válido: usa letras sin tilde, números, espacios y - _ . (máximo 32 caracteres)."
    if any(c["nombre"].lower() == nombre.lower() for c in await vpn.listar()):
        return f"Ya existe un dispositivo llamado «{nombre}» en la VPN."
    cid = await vpn.crear(nombre)
    return (f"Dispositivo «{nombre}» creado (id {cid}). Para conectarlo, abre Centro de control → HEIMDALL "
            "y pulsa «QR» en ese dispositivo para escanearlo con la app WireGuard.")


async def _cambiar_dispositivo(nombre: str, activo: bool) -> str:
    cl = await vpn.listar()
    c = next((x for x in cl if x["nombre"].lower() == str(nombre).strip().lower()), None)
    if not c:
        return "No encuentro ese dispositivo. Dispositivos: " + (", ".join(x["nombre"] for x in cl) or "ninguno") + "."
    await vpn.activar(c["id"], activo)
    return f"Dispositivo «{c['nombre']}» {'activado' if activo else 'desactivado'}."


@tool("activar_dispositivo_vpn", "Activa un dispositivo de la VPN HEIMDALL buscándolo por su nombre.",
      {"nombre": ("string", "Nombre del dispositivo")}, ("nombre",))
async def activar_dispositivo_vpn(nombre: str) -> str:
    return await _cambiar_dispositivo(nombre, True)


@tool("desactivar_dispositivo_vpn", "Desactiva un dispositivo de la VPN HEIMDALL buscándolo por su nombre (pierde el acceso hasta que se active).",
      {"nombre": ("string", "Nombre del dispositivo")}, ("nombre",))
async def desactivar_dispositivo_vpn(nombre: str) -> str:
    return await _cambiar_dispositivo(nombre, False)
