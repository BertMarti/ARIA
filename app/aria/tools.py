"""Herramientas que el modelo puede invocar (tool calling de Ollama).

Para anadir una herramienta nueva basta con decorar una funcion con @tool:

    @tool("mi_herramienta", "Que hace (en espanol)", {"param": ("string", "descripcion")})
    async def mi_herramienta(param: str) -> str:
        return "resultado"

Debe devolver un str o algo serializable a JSON. Los errores se capturan en
ejecutar() y se devuelven al modelo como texto.
"""
import asyncio
import json
import re
import time
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from . import agenda, busqueda, config, control, enlaces, escaneo, estadisticas, finanzas, informacion, mapas, memoria, proyectos, recordatorios, red, rutinas, seguridad, services, shield, sistema, spotify, vpn, vpn_ubicaciones

_REGISTRO: dict = {}

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def tool(nombre: str, descripcion: str, params: dict | None = None, requeridos: tuple = (), usa_uid: bool = False,
         especialista: bool = False):
    """`usa_uid=True`: la función recibe `uid` (el usuario del chat), nunca desde los argumentos del modelo.
    `especialista=True`: solo la ofrecen los agentes que la incluyen (no ARIA general)."""
    def deco(fn):
        props = {k: {"type": t, "description": d} for k, (t, d) in (params or {}).items()}
        _REGISTRO[nombre] = {
            "fn": fn,
            "uid": usa_uid,
            "especialista": especialista,
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
                          "estado_sistema", "buscar_en_netflix", "buscar_en_internet", "noticias", "tiempo",
                          "resumir_enlace", "resumen_noticias", "precio", "mis_mercados", "mis_inversiones",
                           "estado_sistema", "buscar_en_netflix", "buscar_en_internet", "noticias", "tiempo",
                           "resumir_enlace", "mapa_ir", "ruta", "sitios_cerca"})
# Memoria personal: la tiene todo rol y siempre actúa sobre los datos del usuario que habla.
MEMORIA = frozenset({"recordar", "olvidar"})
PROYECTOS = frozenset({"nuevo_proyecto", "mis_proyectos", "estado_proyecto", "registrar_decision", "decisiones", "actualizar_proyecto", "cambiar_personalidad"})
# Recordatorios: todo rol, siempre los del usuario que habla.
RECORDATORIOS = frozenset({"recordatorio", "mis_recordatorios", "borrar_recordatorio"})
AGENDA = frozenset({"crear_evento", "mis_eventos", "borrar_evento", "anadir_cumpleanos", "proximos_cumpleanos"})
# Rutinas (gestión desde el chat): todo rol, siempre las del usuario que habla.
GESTION_RUTINAS = frozenset({"crear_rutina", "mis_rutinas", "borrar_rutina"})
# Lo que puede usar una rutina programada: SOLO consultas (nada que cambie la casa, los datos ni la memoria,
# ni crear o borrar recordatorios/rutinas, ni gastar ancho de banda con un test de velocidad o un escaneo).
# Se cruza además con las del rol y las del agente.
RUTINAS = frozenset(SOLO_LECTURA | {
    "estado_red", "dispositivos_red", "dispositivos_nuevos", "medir_latencia", "informe_seguridad", "estado_escaneo",
    "bloqueos_por_cliente", "resumen_mes", "gastos_por_categoria", "comparar_meses", "estado_presupuestos",
    "buscar_movimientos", "mis_recordatorios", "mis_rutinas"})


# Además, el rol `usuario` puede usar sus finanzas (solo sus datos) y la salud de la red (solo lectura).
DE_USUARIO = frozenset({"registrar_movimiento", "resumen_mes", "gastos_por_categoria", "comparar_meses",
                        "presupuesto", "estado_presupuestos", "buscar_movimientos", "estado_red"})


def permitidas(rol: str) -> set:
    """Nombres de herramientas que ese rol puede ver y ejecutar."""
    if rol == "admin":
        return set(_REGISTRO)
    if rol == "usuario":
        de_modulos = {n for n, i in _DE_MODULOS.items() if i["usuario"]}
    return set(SOLO_LECTURA | MEMORIA | PROYECTOS | RECORDATORIOS | AGENDA | GESTION_RUTINAS | DE_USUARIO | de_modulos) & set(_REGISTRO)
    return set()


def generales() -> set:
    """Herramientas de ARIA general (las de los especialistas no se ofrecen sin su agente)."""
    return {n for n, t in _REGISTRO.items() if not t["especialista"]}


def especificaciones(nombres=None) -> list:
    return [t["spec"] for n, t in _REGISTRO.items() if nombres is None or n in nombres]


# Los modelos pequenos (3B) llaman herramientas sin motivo si se les ofrecen todas.
# Solo se ofrecen las relacionadas con lo que pide el usuario (palabras clave).
# Un patron que empieza por "!" debe NO aparecer en el mensaje.
_BLOQUEADOR = r"\b(bloqueador|anuncios?|publicidad|pi-?hole|shield|adblock|ads)\b"
_SISTEMA = (r"\b(raspberry|rasp|ram|cpu|uptime|procesador|servidor|temperatura|memoria|disco|"
            r"almacenamiento|espacio|sistema)\b")
_EXPLICAR = r"!\b(expl[ií]ca\w*|qu[eé] es|qu[eé] significa|para qu[eé] sirve)\b"  # preguntas conceptuales
# Búsqueda en internet: petición explícita, noticias o datos que cambian con el tiempo.
_BUSCAR = (r"\b(b[uú]sca\w*|busque\w*|googlea\w*|investiga\w*|internet|google|en la red|en la web|online|"
           r"wikipedia)\b")
_NOTICIAS = r"\b(noticias?|titulares?|actualidad|[uú]ltima hora|novedades)\b"
_DATO_ACTUAL = (r"\b(precio|cotizaci[oó]n|resultado|qui[eé]n gan[oó]|qui[eé]n ha ganado|cu[aá]ndo (es|son|fue|juega|sale|"
                r"se estrena)|[uú]ltim[oa]s?|esta semana|este a[nñ]o|clasificaci[oó]n|partido|elecciones|"
                r"cu[aá]nto cuesta|cu[aá]nto vale)\b")
_CUANDO = (r"\b(en \d+ ?(min\w*|h|horas?|d[ií]as?)|en (media|una) hora|dentro de|ma[nñ]ana|pasado ma[nñ]ana|hoy|"
           r"esta (tarde|noche)|a las? \d|a mediod[ií]a|el (lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)|"
           r"todos los|cada (d[ií]a|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo))\b")
_INTENCIONES = [
    ((r"\b(agenda|calendario|evento|eventos|cita|cumplea[nñ]os|qué tengo|que tengo)\b",), set(AGENDA)),
    ((r"\b(mapa|mapas|ubicaci[oó]n|sitios? cerca|farmacia|gasolinera|supermercado|restaurante|cajero)\b",),
     {"mapa_ir", "sitios_cerca"}),
    ((r"\b(ruta|c[oó]mo llego|cu[aá]nto se tarda|indicaciones|ir desde|llevarme)\b",), {"ruta"}),
    ((r"\b(tiempo|llover[aá]?|llueve|lluvia|calor|fr[ií]o|previsi[oó]n|nublado|soleado|tormenta|grados)\b",
      r"!\b(raspberry|cpu|procesador|cu[aá]nto tiempo|encendid[ao])\b"), {"tiempo"}),
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
    ((r"\b(vpn|wireguard|heimdall)\b", r"\b(ubicaci[oó]n|d[oó]nde|desde qu[eé] sitio|conexiones)\b"),
      {"ubicaciones_vpn"}),
    ((r"\b(vpn|wireguard|heimdall)\b",
      r"\b(a[ñn]ad\w*|cre[ao]\w*|nuev[oa]s?|agreg\w+|dar de alta|alta)\b", _EXPLICAR), {"crear_dispositivo_vpn"}),
    ((r"\b(vpn|wireguard|heimdall|dispositivos?)\b",
      r"\b(activa|activar|act[ií]valo|desactiva|desactivar|desact[ií]valo|habilita|deshabilita|apaga|apagar|enciende|encender)\b",
      _EXPLICAR), {"activar_dispositivo_vpn", "desactivar_dispositivo_vpn", "dispositivos_vpn"}),
    ((r"\b(raspberry|rasp|uptime|procesador)\b", _EXPLICAR), {"estado_sistema"}),
    ((r"\b(temperatura|memoria|ram|cpu|disco|almacenamiento|espacio|sistema)\b",
      r"\b(libre|libres|queda\w*|usad\w+|ocupad\w+|tiene|estado|c[oó]mo|cu[aá]nt\w+|qu[eé])\b", _EXPLICAR),
     {"estado_sistema"}),
    ((r"\b(en directo|telemetr[ií]a|contenedor(?:es)?|picos? de cpu)\b",), {"sistema_en_directo"}),
    ((r"\b(spotify|m[uú]sica|canci[oó]n|canciones|pon|ponme|reproduce|pausa|para la|siguiente|anterior|suena|sonando|artista|disco|[aá]lbum)\b",
      r"!" + _BLOQUEADOR, r"!\b(raspberry|ram|cpu|espacio|libre|temperatura)\b"),
     {"spotify_play", "spotify_pause", "spotify_siguiente", "spotify_anterior", "spotify_actual",
      "spotify_buscar_y_reproducir"}),
    ((_BUSCAR, r"!\b(netflix|spotify)\b"), {"buscar_en_internet"}),
    ((_NOTICIAS,), {"noticias"}),
    ((_DATO_ACTUAL, r"!" + _BLOQUEADOR, r"!" + _SISTEMA, r"!\b(vpn|wireguard|heimdall|spotify)\b", _EXPLICAR),
     {"buscar_en_internet"}),
    ((r"\b(netflix|serie|series|pel[ií]cula|pel[ií]culas|cap[ií]tulo)\b",), {"buscar_en_netflix"}),
    ((r"\b(resumen|res[uú]meme|titulares?|noticias?)\b", r"\b(tema|actualidad|tecnolog[ií]a|econom[ií]a|deportes?|ciencia|espa[nñ]a)\b"), {"resumen_noticias"}),
    ((r"\b(precio|cotizaci[oó]n|valor)\b", r"\b(bitcoin|btc|ethereum|eth|ibex|apple|acciones?|bolsa)\b"), {"precio"}),
    ((r"\b(mercados?|inversiones?|cartera|bolsa)\b",), {"mis_mercados", "mis_inversiones"}),
    # Memoria personal: «recuerda que…», «apunta que…» / «olvida que…», «no recuerdes…»
    ((r"\b(recuerda|acu[eé]rdate|ac[eé]rdate|apunta|anota|memoriza|ten en cuenta)\b",), {"recordar"}),
    ((r"\brecu[eé]rdame\b", r"!" + _CUANDO), {"recordar", "recordatorio"}),
    # Recordatorios: «recuérdame mañana a las 9…», «avísame en 20 minutos», «ponme un recordatorio».
    ((r"\b(recu[eé]rdame|av[ií]same|recordatorio|alarma)\b", r"!\b(mis|qu[eé]|cu[aá]les|borra\w*|quita\w*|elimina\w*|cancela\w*)\b"),
     {"recordatorio"}),
    ((r"\b(recuerda|apunta|anota)\b", _CUANDO, r"!\bque\b"), {"recordatorio"}),
    ((r"\brecordatorios?\b", r"\b(mis|qu[eé]|cu[aá]les|tengo|lista\w*|pendientes?)\b"), {"mis_recordatorios"}),
    ((r"\brecordatorios?\b", r"\b(borra\w*|quita\w*|elimina\w*|cancela\w*)\b"), {"borrar_recordatorio", "mis_recordatorios"}),
    ((r"\b(olvida\w*|no recuerdes|deja de recordar|borra\w* (de )?(tu )?memoria)\b",), {"olvidar"}),
    ((r"\b(proyecto|decid[ií]|decidimos|hemos decidido|en qu[eé] estoy|qu[eé] decidimos)\b",), PROYECTOS),
    ((r"\b(s[eé] m[aá]s sincera|vuelve a ser amable|responde m[aá]s breve)\b",), {"cambiar_personalidad"}),
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


_ERRORES_LEGIBLES = (spotify.SpotifyError, shield.ShieldError, vpn.VpnError, finanzas.FinanzasError,
                     red.RedError, escaneo.EscaneoError, control.ControlError)


def registrar_errores(*clases) -> None:
    """Otros módulos añaden sus excepciones «legibles» (mensaje en español para el modelo)."""
    global _ERRORES_LEGIBLES
    _ERRORES_LEGIBLES = tuple(dict.fromkeys(_ERRORES_LEGIBLES + clases))


registrar_errores(estadisticas.EstadisticasError)


async def ejecutar(nombre: str, args: dict | None, rol: str = "admin", uid: int | None = None,
                   solo: set | None = None) -> str:
    """Ejecuta una herramienta comprobando el rol y, si se da `solo`, las del agente activo.
    Las de memoria usan el usuario fijado en `memoria.uid_actual` por el chat; las de datos propios, `uid`."""
    t = _REGISTRO.get(nombre)
    if not t:
        return f"Herramienta desconocida: {nombre}"
    if nombre not in permitidas(rol) or (solo is not None and nombre not in solo):
        return "No tienes permiso para esa acción: pídesela al administrador."
    args = {k: v for k, v in (args or {}).items() if k != "uid"} if isinstance(args, dict) else {}
    if t["uid"]:
        if uid is None:
            return "No sé qué usuario eres; vuelve a entrar en ARIA."
        args["uid"] = uid
    try:
        res = await t["fn"](**args)
    except _ERRORES_LEGIBLES as e:
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


@tool("buscar_en_internet",
      "Busca información actual en internet (datos recientes, hechos, precios, resultados, lugares...). "
      "Devuelve títulos, extractos y enlaces; cita siempre las fuentes al final de la respuesta.",
      {"consulta": ("string", "Qué buscar, con palabras clave concretas")}, ("consulta",))
async def buscar_en_internet(consulta: str) -> str:
    try:
        return busqueda.formatear(str(consulta), await busqueda.buscar(str(consulta), "general", 5))
    except busqueda.BusquedaError as e:
        return str(e)


@tool("noticias",
      "Últimos titulares de noticias en español (de las últimas horas o de la semana). "
      "Sin tema devuelve la actualidad general de España; cita siempre las fuentes.",
      {"tema": ("string", "Tema opcional (p. ej. «economía», «Real Madrid», «Jaén»); vacío = actualidad general")})
async def noticias(tema: str = "") -> str:
    q = " ".join(str(tema or "").split()) or "última hora España"
    try:
        res = await busqueda.buscar(q, "news", 5, "day")
        if len(res) < 3:  # pocas de hoy: se completa con las de la semana
            vistos = {r["dominio"] for r in res}
            res = res + [r for r in await busqueda.buscar(q, "news", 5, "week") if r["dominio"] not in vistos]
            res = res[:5]
        return busqueda.formatear(q, res)
    except busqueda.BusquedaError as e:
        return str(e)


@tool("resumen_noticias", "Resume las noticias recientes de un tema y conserva los enlaces de las fuentes.",
      {"tema": ("string", "Tema de las noticias")}, ("tema",))
async def resumen_noticias(tema: str) -> str:
    try:
        d = await informacion.resumen(tema[:40])
        if d["sin_nube"]:
            return "Titulares (no hay cerebro en la nube):\n" + "\n".join(f"- {x['titulo']} {x['url']}" for x in d["titulares"])
        return d["resumen"] + "\nFuentes:\n" + "\n".join(x["url"] for x in d["titulares"])
    except (busqueda.BusquedaError, informacion.InformacionError) as e:
        return str(e)


@tool("precio", "Consulta el precio actual de una acción, índice, divisa o criptomoneda.",
      {"simbolo": ("string", "Nombre o símbolo, por ejemplo bitcoin, ibex o AAPL")}, ("simbolo",))
async def precio(simbolo: str) -> str:
    try:
        x = informacion._valor(simbolo)
        dato = (await informacion._coingecko([x["simbolo"]]))[0] if x["tipo"] == "cripto" else await informacion.yahoo(x["simbolo"])
        if dato.get("error"): return dato["error"]
        return f"{x.get('nombre', simbolo)}: {dato.get('precio')} {dato.get('divisa', 'EUR')} (variación diaria: {dato.get('variacion', 'sin datos')})."
    except informacion.InformacionError as e:
        return str(e)


@tool("mis_mercados", "Consulta un resumen de los mercados y valores del seguimiento del usuario.", usa_uid=True)
async def mis_mercados(uid: int) -> str:
    d = await informacion.mercados(uid)
    return "\n".join(f"{x.get('nombre', x['simbolo'])}: {x.get('precio', x.get('error', 'sin datos'))} {x.get('divisa', '')}" for x in d["valores"])


@tool("mis_inversiones", "Resume la cartera y su evolución para el usuario actual.", usa_uid=True)
async def mis_inversiones(uid: int) -> str:
    d = await informacion.mercados(uid)
    partes = []
    for x in d["valores"]:
        if (x.get("cantidad") is not None and x.get("precio") is not None
                and x.get("precio_medio") is not None and x.get("valor_posicion") is not None):
            diaria = x.get("variacion_dia", x.get("variacion"))
            diaria = "sin datos" if diaria is None else f"{diaria:+.2f} %"
            partes.append(f"{x['nombre']}: {x['cantidad']} unidades, {x['valor_posicion']:.2f} EUR, "
                          f"ganancia/pérdida {x['ganancia_euros']:+.2f} EUR ({x['ganancia_porcentaje']:+.2f} %), "
                          f"variación diaria {diaria}")
        else:
            partes.append(f"{x['nombre']}: {x.get('precio', x.get('error', 'sin datos'))} {x.get('divisa', '')}")
    return "Tu cartera hoy: " + "; ".join(partes)


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


@tool("tiempo", "Previsión del tiempo por días (cielo, máxima, mínima y probabilidad de lluvia). Úsala para "
      "cualquier pregunta sobre el tiempo, la lluvia o la temperatura exterior, también de fin de semana o próximos días.",
      {"ciudad": ("string", "Ciudad (opcional; por defecto la del usuario)")})
async def tiempo(ciudad: str = "", **_ignorado) -> str:
    from . import briefing
    p = await briefing.prevision(7, ciudad or None)  # siempre 7 días: el modelo no elige un rango corto por error
    if not p:
        return "No hay previsión disponible (falta ARIA_CIUDAD o no responde el servicio del tiempo)."
    etiqueta = {0: "HOY ", 1: "MAÑANA "}
    finde = {"sábado", "domingo"}
    filas = [f"{etiqueta.get(i, '')}{d['dia']} {d['fecha'][8:]}/{d['fecha'][5:7]}"
             f"{' (FIN DE SEMANA)' if d['dia'] in finde else ''}: {d['cielo']}, "
             f"mínima {d['min']} °C, máxima {d['max']} °C, lluvia {d['lluvia']} %" for i, d in enumerate(p["dias"])]
    return (f"Previsión para {p['ciudad']} (usa SOLO estos días; si preguntan por un día que no aparece, dilo):\n"
            + "\n".join(filas))


@tool("mapa_ir", "Abre el mapa centrado en un lugar. No realiza ninguna acción externa.",
      {"lugar": ("string", "Lugar, dirección o coordenadas lat,lon (vacío = casa)")})
async def mapa_ir(lugar: str = "") -> str:
    try:
        lat, lon, nombre = await mapas._resolver(lugar)
        return f"Mapa centrado en {nombre}: {mapas._enlace(f'{lat},{lon}')}"
    except mapas.MapasError as e:
        return str(e)


@tool("ruta", "Calcula una ruta y devuelve distancia, duración y un enlace para abrirla en el mapa.",
      {"desde": ("string", "Origen, dirección o coordenadas"), "hasta": ("string", "Destino, dirección o coordenadas"),
       "modo": ("string", "driving, foot o bike; por defecto driving")}, ("desde", "hasta"))
async def ruta(desde: str, hasta: str, modo: str = "driving") -> str:
    try:
        if modo not in ("driving", "foot", "bike"):
            return "El modo debe ser driving, foot o bike."
        a, b = await asyncio.gather(mapas._resolver(mapas._texto(desde)), mapas._resolver(mapas._texto(hasta)))
        datos = await mapas._get(f"{mapas.OSRM}/route/v1/{modo}/{a[1]},{a[0]};{b[1]},{b[0]}",
                                 params={"overview": "false"})
        r = (datos.get("routes") or [None])[0]
        if not r:
            return "No se ha encontrado una ruta entre esos lugares."
        minutos = round(float(r.get("duration", 0)) / 60)
        distancia = float(r.get("distance", 0))
        enlace = f"#mapa?desde={quote(f'{a[0]},{a[1]}')}&hasta={quote(f'{b[0]},{b[1]}')}"
        return (f"Ruta de {a[2]} a {b[2]}: {distancia / 1000:.1f} km, unos {minutos} minutos. "
                f"Abrir en el mapa: {enlace}")
    except mapas.MapasError as e:
        return str(e)


@tool("sitios_cerca", "Busca los cinco sitios más cercanos de una categoría y da su distancia.",
      {"tipo": ("string", "farmacia, gasolinera, supermercado, restaurante o cajero"),
       "lugar": ("string", "Centro de búsqueda opcional; por defecto casa")}, ("tipo",))
async def sitios_cerca(tipo: str, lugar: str = "") -> str:
    try:
        if tipo not in mapas._TIPOS:
            return "Tipo no permitido: farmacia, gasolinera, supermercado, restaurante o cajero."
        lat, lon, nombre = await mapas._resolver(lugar)
        filtro, _ = mapas._TIPOS[tipo]
        datos = await mapas._get(mapas.OVERPASS, params={"data": f"[out:json][timeout:10];nwr[{filtro}](around:5000,{lat},{lon});out center;"})
        sitios = []
        for x in datos.get("elements", []) if isinstance(datos, dict) else []:
            p = x.get("center", x)
            if p.get("lat") and p.get("lon"):
                d = round(mapas._distancia(lat, lon, float(p["lat"]), float(p["lon"])))
                sitios.append(((x.get("tags") or {}).get("name") or "Sin nombre", d))
        sitios.sort(key=lambda x: x[1])
        if not sitios:
            return f"No encuentro {tipo}s cerca de {nombre}."
        return f"{tipo.capitalize()} cerca de {nombre}: " + "; ".join(f"{n} ({mapas._formato_distancia(d)})" for n, d in sitios[:5]) + "."
    except mapas.MapasError as e:
        return str(e)


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


@tool("sistema_en_directo", "Consulta la telemetría reciente de la Raspberry y sus contenedores. Solo lectura.")
async def sistema_en_directo() -> str:
    from . import telemetria
    try:
        return await asyncio.to_thread(telemetria.texto)
    except RuntimeError as e:
        return str(e)


@tool("crear_dispositivo_vpn",
      "Crea un dispositivo nuevo (móvil, portátil...) en la VPN HEIMDALL. No devuelve claves: el usuario escanea el QR en la web.",
     {"nombre": ("string", "Nombre del dispositivo (letras sin tilde, números, espacios y - _ .; máximo 32)")}, ("nombre",))
async def crear_dispositivo_vpn(nombre: str, caduca: str = "") -> str:
    nombre = str(nombre).strip()
    if not vpn.nombre_valido(nombre):
        return "Nombre no válido: usa letras sin tilde, números, espacios y - _ . (máximo 32 caracteres)."
    if any(c["nombre"].lower() == nombre.lower() for c in await vpn.listar()):
        return f"Ya existe un dispositivo llamado «{nombre}» en la VPN."
    cid = await vpn.crear(nombre, caduca or None)
    return (f"Dispositivo «{nombre}» creado (id {cid}). Para conectarlo, abre Centro de control → HEIMDALL "
            "y pulsa «QR» en ese dispositivo para escanearlo con la app WireGuard.")


@tool("ubicaciones_vpn", "Consulta las últimas ubicaciones conocidas de los dispositivos VPN (solo lectura).",
      {"dispositivo": ("string", "Nombre o id del dispositivo; vacío = todos")})
async def ubicaciones_vpn(dispositivo: str = "") -> str:
    clientes = await vpn.listar()
    texto = str(dispositivo).strip().lower()
    if texto:
        clientes = [c for c in clientes if str(c["id"]) == texto or c["nombre"].lower() == texto]
    filas = []
    for c in clientes:
        hs = vpn_ubicaciones.historial(c["id"], 10)
        filas.append(c["nombre"] + ": " + ("; ".join(f"{x['ciudad']}, {x['pais']} ({x['operador']})" for x in hs) or "sin ubicaciones aprendidas"))
    return "\n".join(filas) or "No encuentro ese dispositivo VPN."


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


@tool("recordar",
      "Guarda un dato personal del usuario (algo suyo, de su casa o de sus preferencias) para recordarlo en "
      "futuras conversaciones. Úsala cuando diga «recuerda que…», «apunta que…» o similar.",
      {"dato": ("string", "Lo que hay que recordar, en una frase corta (máximo 300 caracteres)")}, ("dato",))
async def recordar(dato: str) -> str:
    uid = memoria.uid_actual.get()
    if uid is None:
        return "No sé quién eres, no puedo guardar recuerdos ahora."
    try:
        rec, nuevo = memoria.anadir(uid, str(dato), "usuario")
    except memoria.MemoriaError as e:
        return str(e)
    if not nuevo:
        return f"Ya lo tenía anotado: «{rec['texto']}»."
    return f"Anotado: «{rec['texto']}». Puedes verlo o borrarlo en Ajustes → Memoria."


@tool("olvidar",
      "Borra un recuerdo del usuario. Admite el número del recuerdo o unas palabras de lo que debe olvidar. "
      "Úsala cuando diga «olvida que…» o «no recuerdes…».",
      {"dato_o_id": ("string", "Número del recuerdo o texto (aunque sea parcial) de lo que hay que olvidar")}, ("dato_o_id",))
async def olvidar(dato_o_id: str) -> str:
    uid = memoria.uid_actual.get()
    if uid is None:
        return "No sé quién eres, no puedo borrar recuerdos ahora."
    q = str(dato_o_id)
    hallados = memoria.buscar(uid, q)
    if not hallados:
        return "No tengo ningún recuerdo que encaje con eso."
    if len(hallados) > 1 and not q.strip().lstrip("#").isdigit():
        lista = "; ".join(f"{h['id']}: {h['texto']}" for h in hallados[:5])
        return f"Encajan varios recuerdos ({lista}). Dime cuál olvidar (su número)."
    memoria.borrar(uid, hallados[0]["id"])
    return f"Olvidado: «{hallados[0]['texto']}»."


def _proyecto_por_nombre(uid, nombre):
    n = memoria.normalizar(nombre)
    return next((p for p in proyectos.listar(uid) if memoria.normalizar(p["nombre"]) == n), None)


@tool("cambiar_personalidad", "Cambia la forma de responder de ARIA para este usuario.",
      {"modo": ("string", "amable, sincera o breve"), "discrepar": ("boolean", "si puede discrepar")}, ("modo",))
async def cambiar_personalidad(modo: str, discrepar: bool = False) -> str:
    uid = memoria.uid_actual.get()
    if uid is None:
        return "No sé quién eres, no puedo cambiar tus preferencias."
    try:
        p = memoria.fijar_personalidad(uid, str(modo).lower(), bool(discrepar))
    except memoria.MemoriaError as e:
        return str(e)
    return f"Personalidad cambiada a {p['modo']}" + ("; puedo discrepar." if p["discrepar"] else ".")


@tool("nuevo_proyecto", "Crea un proyecto personal del usuario.",
      {"nombre": ("string", "Nombre"), "descripcion": ("string", "Descripción opcional")}, ("nombre",), usa_uid=True)
async def nuevo_proyecto(nombre: str, descripcion: str = "", uid: int = None) -> str:
    try:
        return json.dumps(proyectos.crear(uid, nombre, descripcion), ensure_ascii=False)
    except proyectos.ProyectoError as e:
        return str(e)


@tool("mis_proyectos", "Lista los proyectos personales del usuario.", usa_uid=True)
async def mis_proyectos(uid: int = None) -> str:
    return json.dumps(proyectos.listar(uid), ensure_ascii=False)


@tool("estado_proyecto", "Consulta un proyecto por su nombre.", {"proyecto": ("string", "Nombre del proyecto")}, ("proyecto",), usa_uid=True)
async def estado_proyecto(proyecto: str, uid: int = None) -> str:
    p = _proyecto_por_nombre(uid, proyecto)
    return json.dumps(p, ensure_ascii=False) if p else "No encuentro ese proyecto."


@tool("registrar_decision", "Registra una decisión en uno de tus proyectos.",
      {"proyecto": ("string", "Nombre"), "decision": ("string", "Decisión"), "motivo": ("string", "Motivo opcional")},
      ("proyecto", "decision"), usa_uid=True)
async def registrar_decision(proyecto: str, decision: str, motivo: str = "", uid: int = None) -> str:
    p = _proyecto_por_nombre(uid, proyecto)
    if not p:
        return "No encuentro ese proyecto."
    try:
        return json.dumps(proyectos.registrar_decision(uid, p["id"], decision, motivo), ensure_ascii=False)
    except proyectos.ProyectoError as e:
        return str(e)


@tool("decisiones", "Lista las decisiones de un proyecto.", {"proyecto": ("string", "Nombre")}, ("proyecto",), usa_uid=True)
async def decisiones(proyecto: str, uid: int = None) -> str:
    p = _proyecto_por_nombre(uid, proyecto)
    return json.dumps(proyectos.decisiones(uid, p["id"]), ensure_ascii=False) if p else "No encuentro ese proyecto."


@tool("actualizar_proyecto", "Actualiza el estado de un proyecto, sin borrarlo.",
      {"proyecto": ("string", "Nombre"), "estado": ("string", "idea, en_curso, pausado o terminado")},
      ("proyecto", "estado"), usa_uid=True)
async def actualizar_proyecto(proyecto: str, estado: str, uid: int = None) -> str:
    p = _proyecto_por_nombre(uid, proyecto)
    if not p:
        return "No encuentro ese proyecto."
    try:
        return json.dumps(proyectos.actualizar(uid, p["id"], estado=estado), ensure_ascii=False)
    except proyectos.ProyectoError as e:
        return str(e)


@tool("crear_evento", "Crea un evento personal en la agenda.",
      {"titulo": ("string", "Título del evento"), "cuando": ("string", "Fecha ISO o frase como mañana a las 10"),
       "duracion_min": ("integer", "Duración en minutos, opcional"), "lugar": ("string", "Lugar opcional"),
       "repeticion": ("string", "ninguna, semanal, mensual o anual"), "aviso_min": ("integer", "Minutos antes, opcional")},
      ("titulo", "cuando"), usa_uid=True)
async def crear_evento(uid, titulo, cuando, duracion_min=None, lugar="", repeticion="ninguna", aviso_min=None):
    try:
        inicio, rep = recordatorios.interpretar(cuando)
        datos = {"titulo": titulo, "inicio": inicio.isoformat(), "lugar": lugar,
                 "repeticion": rep or repeticion or "ninguna", "aviso_min": aviso_min}
        if duracion_min:
            datos["fin"] = (inicio + __import__("datetime").timedelta(minutes=int(duracion_min))).isoformat()
        e = agenda.crear_evento(uid, datos)
        return f"Evento creado: «{e['titulo']}» el {e['inicio']}."
    except recordatorios.RecordatorioError as e:
        return str(e)
    except (agenda.AgendaError, ValueError) as e:
        return str(e)


@tool("mis_eventos", "Lista tus eventos de agenda en un rango.",
      {"desde": ("string", "Inicio ISO opcional"), "hasta": ("string", "Final ISO opcional")}, usa_uid=True)
async def mis_eventos(uid, desde=None, hasta=None):
    hoy = __import__("datetime").date.today()
    try:
        eventos = agenda.listar_eventos(uid, desde or hoy.isoformat(), hasta or (hoy + __import__("datetime").timedelta(days=8)).isoformat())
        return "\n".join(f"{e['id']}: {e['titulo']} ({e['inicio']})" for e in eventos) or "No tienes eventos en ese periodo."
    except agenda.AgendaError as e: return str(e)


@tool("borrar_evento", "Borra un evento propio de la agenda. Pide confirmación al usuario antes de hacerlo.",
      {"id": ("integer", "Identificador del evento")}, ("id",), usa_uid=True)
async def borrar_evento(uid, id):
    return "Evento borrado." if agenda.borrar_evento(uid, int(id)) else "No encuentro ese evento."


@tool("anadir_cumpleanos", "Añade un cumpleaños a tu agenda.",
      {"nombre": ("string", "Nombre"), "dia": ("integer", "Día"), "mes": ("integer", "Mes"), "anio": ("integer", "Año opcional")},
      ("nombre", "dia", "mes"), usa_uid=True)
async def anadir_cumpleanos(uid, nombre, dia, mes, anio=None):
    try: c = agenda.crear_cumple(uid, {"nombre": nombre, "dia": dia, "mes": mes, "anio": anio})
    except agenda.AgendaError as e: return str(e)
    return f"Cumpleaños añadido: {c['nombre']} ({c['dia']}/{c['mes']})."


@tool("proximos_cumpleanos", "Lista los próximos cumpleaños personales.", {"dias": ("integer", "Días a consultar")}, usa_uid=True)
async def proximos_cumpleanos(uid, dias=30):
    try: cs = agenda.listar_cumpleanos(uid, dias)
    except (agenda.AgendaError, ValueError) as e: return str(e)
    return "\n".join(f"{c['nombre']}: {c['fecha']}" + (f" (cumple {c['edad']})" if c.get("edad") is not None else "") for c in cs) or "No hay cumpleaños próximos."


# --- Finanzas (datos del usuario que chatea) ---------------------------------------------------------
_MES = ("string", "Mes en formato AAAA-MM (vacío = el mes actual)")


def _lista_cats(cats: list, n: int = 8) -> str:
    return ", ".join(f"{c['categoria']} {finanzas.euros(c['total'])}" for c in cats[:n]) or "sin gastos"


@tool("registrar_movimiento", "Apunta un gasto (importe negativo) o un ingreso (positivo) en las finanzas del usuario.",
      {"concepto": ("string", "Concepto, p. ej. 'Mercadona'"),
       "importe": ("number", "Importe en euros: negativo si es gasto, positivo si es ingreso"),
       "fecha": ("string", "Fecha dd/mm/aaaa o aaaa-mm-dd (vacío = hoy)"),
       "categoria": ("string", "Categoría (opcional; se adivina si falta)"),
       "cuenta": ("string", "Cuenta o tarjeta (opcional)")}, ("concepto", "importe"), usa_uid=True, especialista=True)
async def registrar_movimiento(uid, concepto, importe, fecha=None, categoria=None, cuenta=None) -> str:
    # Desde el chat no se crean categorías nuevas: si no existe, se categoriza automáticamente.
    if categoria and str(categoria).strip().lower() not in {c.lower() for c in finanzas.categorias(uid)}:
        categoria = None
    m = finanzas.registrar(uid, fecha, concepto, importe, categoria, cuenta)
    return (f"Apuntado: {m['concepto']} {finanzas.euros(m['importe'])} el {m['fecha']}"
            f" (categoría: {m['categoria'] or 'sin categoría'}).")


@tool("resumen_mes", "Resumen de las finanzas de un mes: ingresos, gastos, balance y gastos por categoría.",
      {"mes": _MES}, usa_uid=True, especialista=True)
async def resumen_mes(uid, mes=None) -> str:
    r = finanzas.resumen_mes(uid, mes)
    if not r["movimientos"]:
        return f"No hay movimientos en {r['mes']}."
    return (f"{r['mes']}: ingresos {finanzas.euros(r['ingresos'])}, gastos {finanzas.euros(r['gastos'])}, "
            f"balance {finanzas.euros(r['balance'])} ({r['movimientos']} movimientos). "
            f"Gastos por categoría: {_lista_cats(r['categorias'])}.")


@tool("gastos_por_categoria", "Gastos de un mes agrupados por categoría, de mayor a menor.", {"mes": _MES}, usa_uid=True, especialista=True)
async def gastos_por_categoria(uid, mes=None) -> str:
    m = finanzas.mes_valido(mes)
    return f"Gastos de {m} por categoría: {_lista_cats(finanzas.gastos_por_categoria(uid, m), 20)}."


@tool("comparar_meses", "Compara ingresos, gastos y categorías de dos meses.",
      {"mes_a": ("string", "Primer mes AAAA-MM"), "mes_b": ("string", "Segundo mes AAAA-MM")},
      ("mes_a", "mes_b"), usa_uid=True, especialista=True)
async def comparar_meses(uid, mes_a, mes_b) -> str:
    c = finanzas.comparar_meses(uid, mes_a, mes_b)
    a, b = c["a"], c["b"]
    dif = ", ".join(f"{x['categoria']} {'+' if x['diferencia'] >= 0 else ''}{finanzas.euros(x['diferencia'])}"
                    for x in c["categorias"][:6] if x["diferencia"])
    return (f"{a['mes']}: gastos {finanzas.euros(a['gastos'])}, ingresos {finanzas.euros(a['ingresos'])}. "
            f"{b['mes']}: gastos {finanzas.euros(b['gastos'])}, ingresos {finanzas.euros(b['ingresos'])}. "
            f"Diferencia de gasto ({b['mes']} - {a['mes']}): {finanzas.euros(b['gastos'] - a['gastos'])}. "
            f"Cambios por categoría: {dif or 'ninguno'}.")


@tool("presupuesto", "Fija (o quita con 0) el presupuesto mensual de una categoría.",
      {"categoria": ("string", "Categoría"), "importe": ("number", "Euros al mes (0 = quitar)")},
      ("categoria", "importe"), usa_uid=True, especialista=True)
async def presupuesto(uid, categoria, importe) -> str:
    p = finanzas.fijar_presupuesto(uid, categoria, importe)
    if not p["importe"]:
        return f"Presupuesto de {p['categoria']} eliminado."
    return f"Presupuesto mensual de {p['categoria']}: {finanzas.euros(p['importe'])}."


@tool("estado_presupuestos", "Cuánto se lleva gastado de cada presupuesto en un mes.", {"mes": _MES}, usa_uid=True, especialista=True)
async def estado_presupuestos(uid, mes=None) -> str:
    m = finanzas.mes_valido(mes)
    e = finanzas.estado_presupuestos(uid, m)
    if not e:
        return "No hay presupuestos definidos."
    return f"Presupuestos de {m}: " + "; ".join(
        f"{x['categoria']}: {finanzas.euros(x['gastado'])} de {finanzas.euros(x['presupuesto'])} ({x['porcentaje']} %"
        f"{', SUPERADO' if x['superado'] else ''})" for x in e) + "."


@tool("buscar_movimientos", "Busca movimientos por texto del concepto, mes o categoría.",
      {"texto": ("string", "Texto a buscar en el concepto"), "mes": _MES, "categoria": ("string", "Categoría")},
      usa_uid=True, especialista=True)
async def buscar_movimientos(uid, texto=None, mes=None, categoria=None) -> str:
    r = finanzas.listar(uid, mes or None, categoria or None, texto or None, limite=15)
    if not r:
        return "No he encontrado movimientos."
    total = sum(m["importe"] for m in r)
    return f"{len(r)} movimiento(s) (suma {finanzas.euros(total)}): " + "; ".join(
        f"{m['fecha']} {m['concepto']} {finanzas.euros(m['importe'])}" for m in r) + "."



# --- Redes ---------------------------------------------------------------------------------------------
def _lat_texto(lat: dict) -> str:
    return "; ".join(f"{d['nombre']} {d['media_ms']} ms" + (f" ({d['perdida']} % perdidos)" if d["perdida"] else "")
                     if d["media_ms"] is not None else f"{d['nombre']} sin respuesta" for d in lat["destinos"])


@tool("estado_red", "Salud de la red: latencia al router y a Internet, DNS (SHIELD), VPN y último test de velocidad.",
      especialista=True)
async def estado_red() -> str:
    s = await red.salud()
    v = s["velocidad"]
    vel = (f"Último test de velocidad: {v['bajada_mbps']} Mbps de bajada y {v['subida_mbps']} de subida "
           f"({time.strftime('%d/%m %H:%M', time.localtime(v['ts']))})." if v else "No hay ningún test de velocidad aún.")
    vpn_t = (f"VPN: {s['vpn']}, {s['vpn_clientes']['conectados']} de {s['vpn_clientes']['dispositivos']} dispositivos conectados."
             if s["vpn_clientes"] else f"VPN: {s['vpn']}.")
    return f"Latencia: {_lat_texto(s['latencia'])}. DNS: {s['dns']}. {vpn_t} {vel}"


@tool("dispositivos_red", "Lista los dispositivos de la red de casa (nombre, IP, fabricante, si es conocido).",
      especialista=True)
async def dispositivos_red() -> str:
    ds = await red.dispositivos()
    if not ds:
        return "No he encontrado dispositivos (¿está conectado SHIELD-DNS o hay algún escaneo?)."
    partes = [f"{d.get('alias') or d.get('nombre') or d.get('fabricante') or 'sin nombre'} {d['ip']}"
              f"{'' if d['conocido'] else ' (NO reconocido)'}" for d in ds[:60]]
    return f"{len(ds)} dispositivo(s): " + "; ".join(partes) + "."


@tool("dispositivos_nuevos", "Dispositivos de la red que aún no se han marcado como conocidos.", especialista=True)
async def dispositivos_nuevos() -> str:
    ds = [d for d in await red.dispositivos() if not d["conocido"]]
    if not ds:
        return "No hay dispositivos sin reconocer."
    return f"{len(ds)} sin reconocer: " + "; ".join(
        f"{d.get('nombre') or d.get('fabricante') or 'sin nombre'} {d['ip']} (visto por primera vez "
        f"{time.strftime('%d/%m %H:%M', time.localtime(d['primera_vez']))})" for d in ds[:40]) + "."


@tool("marcar_dispositivo_conocido", "Marca un dispositivo de la red como conocido (por su IP o nombre) y opcionalmente le pone un alias.",
      {"dispositivo": ("string", "IP o nombre del dispositivo"), "alias": ("string", "Nombre para recordarlo (opcional)")},
      ("dispositivo",), especialista=True)
async def marcar_dispositivo_conocido(dispositivo, alias=None) -> str:
    await red.dispositivos()
    clave = await asyncio.to_thread(red.buscar_clave, dispositivo)
    if not clave:
        return "No encuentro ese dispositivo en el inventario."
    await asyncio.to_thread(red.marcar_conocido, clave, True, alias)
    return f"Dispositivo {dispositivo} marcado como conocido" + (f" con el alias «{alias}»." if alias else ".")


@tool("medir_latencia", "Mide ahora la latencia (ping) al router, a 1.1.1.1 y a 8.8.8.8.", especialista=True)
async def medir_latencia() -> str:
    return "Latencia media: " + _lat_texto(await red.latencia()) + "."


@tool("test_velocidad", "Hace un test de velocidad de Internet (unos 20 MB; como mucho uno cada 10 minutos).",
      especialista=True)
async def test_velocidad() -> str:
    v = await red.velocidad()
    return (f"Velocidad: {v['bajada_mbps']} Mbps de bajada, {v['subida_mbps']} Mbps de subida, latencia "
            f"{v['latencia_ms']} ms (servidor de Cloudflare).")


# --- Seguridad (solo admin) -------------------------------------------------------------------------
@tool("informe_seguridad", "Informe de seguridad defensivo de la red de casa: hallazgos por gravedad y qué hacer.",
      especialista=True)
async def informe_seguridad() -> str:
    return seguridad.texto_informe(await seguridad.informe())


@tool("escanear_red", f"Pide un escaneo de puertos (nmap) de la red de casa {config.RED_PERMITIDA}. Como mucho uno cada 10 minutos.",
      {"perfil": ("string", "'rapido' (100 puertos, por defecto) o 'completo' (1000 puertos)")}, especialista=True)
async def escanear_red(perfil="rapido") -> str:
    perfil = "completo" if str(perfil or "").lower().startswith("compl") else "rapido"
    pid = await asyncio.to_thread(escaneo.solicitar, perfil, None, "chat")
    return (f"Escaneo {perfil} solicitado (id {pid}). Tarda unos minutos; luego pide el informe de seguridad.")


@tool("estado_escaneo", "Estado del escáner: si hay un escaneo en curso y cuándo fue el último.", especialista=True)
async def estado_escaneo() -> str:
    e = await asyncio.to_thread(escaneo.estado)
    if not e["disponible"]:
        return "El escáner aria-escaner no está instalado."
    u = e["ultimo"]
    ult = (f"Último: {u['perfil']} ({u['origen']}) el {time.strftime('%d/%m %H:%M', time.localtime(u['fin'] or 0))}, "
           f"{u['hosts']} equipos." if u else "Aún no hay escaneos.")
    return (f"Escáner {'activo' if e['escaner_vivo'] else 'sin señal'}; "
            f"{'escaneo en curso' if e['en_curso'] else 'sin escaneos en curso'}; pendientes: {e['pendientes']}. {ult}")


@tool("bloqueos_por_cliente", "Dominios más bloqueados por Pi-hole para cada dispositivo (rastreadores, publicidad, posibles malware).",
      especialista=True)
async def bloqueos_por_cliente() -> str:
    b = await seguridad.bloqueos_por_cliente()
    if not b:
        return "No hay datos de bloqueos por dispositivo."
    return " | ".join(f"{c['cliente']}: {c['bloqueadas']} bloqueadas; " + ", ".join(
        f"{d['dominio']} ({d['veces']}, {d['tipo']})" for d in c["dominios"]) for c in b)


@tool("estadisticas_dispositivo", "Estadísticas DNS de un dispositivo: consultas, bloqueos, serie temporal y dominios más consultados.",
      {"dispositivo": ("string", "Alias, IP o MAC del dispositivo (opcional)"),
       "horas": ("integer", "24 o 168 horas")}, especialista=True)
async def estadisticas_dispositivo(dispositivo=None, horas=24) -> str:
    if dispositivo:
        await red.dispositivos()
        clave = await asyncio.to_thread(red.buscar_clave, dispositivo)
        if not clave:
            return "No encuentro ese dispositivo en el inventario."
        d = await estadisticas.detalle(clave, horas)
        top = ", ".join(f"{x['dominio']} ({x['veces']})" for x in d["bloqueados"]) or "ninguno"
        return f"{d['nombre']} ({d['ip']}): dominios bloqueados: {top}."
    r = await estadisticas.resumen(horas)
    return (f"En las últimas {r['horas']} horas: {r['totales']['consultas']} consultas, "
            f"{r['totales']['bloqueadas']} bloqueadas ({r['totales']['porcentaje']} %). "
            + "; ".join(f"{x['nombre']}: {x['consultas']} consultas" for x in r["dispositivos"][:10]) + ".")

# Palabras clave para el cerebro local (los de la nube reciben todas las del agente).
_INTENCIONES += [
    ((r"\b(estad[ií]stic\w*|qu[eé] consulta|cu[aá]nto navega|qu[eé] bloquea|consultas por dispositivo)\b",),
     {"estadisticas_dispositivo"}),
    ((r"\b(gast\w*|pagu[eé]|pagado|compr[eé])\b", r"\b(apunta|anota|registra|a[ñn]ade|he gastado|pagu[eé])\b"),
     {"registrar_movimiento"}),
    ((r"\b(ingres\w*|cobr\w*|n[oó]mina)\b", r"\b(apunta|anota|registra|a[ñn]ade)\b"), {"registrar_movimiento"}),
    ((r"\b(gast\w*|ingres\w*|balance|finanzas|ahorr\w*|dinero)\b", r"\b(mes|resumen|cu[aá]nt\w*|total|este)\b"),
     {"resumen_mes", "gastos_por_categoria"}),
    ((r"\b(categor[ií]as?|en qu[eé])\b", r"\b(gast\w*|dinero)\b"), {"gastos_por_categoria"}),
    ((r"\b(compar\w*|diferencia|frente a|respecto)\b", r"\b(mes|meses|gast\w*|enero|febrero|marzo|abril|mayo|junio|"
      r"julio|agosto|septiembre|octubre|noviembre|diciembre)\b"), {"comparar_meses"}),
    ((r"\bpresupuest\w*\b", r"\b(pon|fija|establece|cambia|quita|define|de)\b", r"!\b(c[oó]mo voy|estado|llevo)\b"),
     {"presupuesto"}),
    ((r"\bpresupuest\w*\b", r"\b(c[oó]mo|estado|llevo|queda|superad\w*|voy)\b"), {"estado_presupuestos"}),
    ((r"\b(busca\w*|movimientos?|cargos?|recibos?)\b", r"\b(gast\w*|pag\w*|movimientos?|cargos?|recibos?|compr\w*)\b"),
     {"buscar_movimientos"}),
]

_INTENCIONES += [
    ((r"\b(red|lan|wifi|wi-fi|internet|conexi[oó]n)\b", r"\b(estado|c[oó]mo|va|funciona\w*|salud|lent\w*)\b"), {"estado_red"}),
    ((r"\b(dispositivos?|equipos?|aparatos?)\b", r"\b(red|lan|wifi|casa|conectad\w+)\b", r"!\b(vpn|wireguard|heimdall)\b",
      r"!\b(nuevos?|desconocid\w+|conocid\w+)\b"), {"dispositivos_red"}),
    ((r"\b(nuevos?|desconocid\w+|sin reconocer|intrus\w*)\b", r"\b(dispositivos?|equipos?|red)\b"), {"dispositivos_nuevos"}),
    ((r"\b(marca\w*|reconoce\w*)\b", r"\bconocid\w*\b"), {"marcar_dispositivo_conocido"}),
    ((r"\b(latencia|ping)\b",), {"medir_latencia"}),
    ((r"\b(velocidad|speed ?test|mbps|test de velocidad)\b",), {"test_velocidad"}),
    ((r"\b(seguridad|vulnerab\w*|riesgos?|hallazgos?|informe)\b", r"!\b(escanea|escaneo nuevo|lanza)\b"), {"informe_seguridad"}),
    ((r"\b(escanea\w*|escaneo|nmap|puertos?)\b", r"\b(lanza|haz|hazme|escanea\w*|nuevo|ahora|empieza)\b"), {"escanear_red"}),
    ((r"\b(escaneo|esc[aá]ner)\b", r"\b(estado|c[oó]mo va|termin\w*|en curso|[uú]ltimo)\b"), {"estado_escaneo"}),
    ((r"\b(bloquead\w*|bloqueos?|rastreadores?|trackers?|malware)\b", r"\b(dispositivos?|clientes?|cada|qui[eé]n|por)\b"),
     {"bloqueos_por_cliente"}),
]



# --- Control parental (solo admin; ver control.py) ---------------------------------------------------------
# Siempre sobre UN dispositivo del inventario (alias, nombre, IP o MAC); nunca «todos», nunca el router ni la Pi.
async def _clave_control(dispositivo) -> str:
    await red.dispositivos()   # refresca el inventario (IP y alias vigentes)
    return await asyncio.to_thread(control.resolver, str(dispositivo or ""))


async def _aplicar_control(texto: str) -> str:
    r = await control.reconciliar()
    if r.get("ok"):
        return f"{texto} {control.LIMITACION_CORTA}"
    return (f"{texto} Queda guardado, pero aún no se ha podido aplicar en SHIELD-DNS ({r.get('error')}); "
            "ARIA lo reintenta cada 30 segundos.")


def _entero(v, defecto=None):
    if v is None or v == "":
        return defecto
    try:
        return int(float(str(v).replace(",", ".")))
    except ValueError:
        raise control.ControlError("Los minutos deben ser un número.") from None


@tool("pausar_internet", "Pausa el internet de UN dispositivo de la red (por DNS): indefinidamente o durante unos minutos. "
      "Después se reanuda solo.",
      {"dispositivo": ("string", "Alias, nombre, IP o MAC del dispositivo (p. ej. «iPad»)"),
       "minutos": ("integer", "Duración en minutos (1 hora = 60). Vacío = hasta que se reanude")},
      ("dispositivo",), especialista=True)
async def pausar_internet(dispositivo, minutos=None) -> str:
    clave = await _clave_control(dispositivo)
    m = _entero(minutos)
    await asyncio.to_thread(control.pausar, clave, m)
    r = await asyncio.to_thread(control._fila, clave)
    cuando = (f"durante {m} minuto(s)" if m else "hasta que se reanude")
    return await _aplicar_control(f"Internet de «{control.nombre_de(r)}» pausado {cuando}.")


@tool("reanudar_internet", "Reanuda el internet de UN dispositivo que estaba pausado.",
      {"dispositivo": ("string", "Alias, nombre, IP o MAC del dispositivo")}, ("dispositivo",), especialista=True)
async def reanudar_internet(dispositivo) -> str:
    clave = await _clave_control(dispositivo)
    hubo = await asyncio.to_thread(control.reanudar, clave)
    r = await asyncio.to_thread(control._fila, clave)
    e = (await asyncio.to_thread(control.estado, clave))[0]
    extra = " Sigue activo un horario de sin internet." if e["por_horario"] else ""
    return await _aplicar_control(f"Internet de «{control.nombre_de(r)}» " + ("reanudado." if hubo else "no estaba pausado.") + extra)


@tool("bloquear_servicio", "Bloquea un servicio (TikTok, YouTube, Instagram, Facebook, Fortnite, Roblox, Twitch, Netflix...) "
      "en UN dispositivo, por DNS.",
      {"dispositivo": ("string", "Alias, nombre, IP o MAC del dispositivo"),
       "servicio": ("string", "Servicio: tiktok, youtube, instagram, facebook, whatsapp, snapchat, x, twitch, discord, "
                              "fortnite, roblox, minecraft, steam, netflix, disneyplus, primevideo")},
      ("dispositivo", "servicio"), especialista=True)
async def bloquear_servicio(dispositivo, servicio) -> str:
    clave = await _clave_control(dispositivo)
    sid = await asyncio.to_thread(control.bloquear_servicio, clave, str(servicio or ""))
    r = await asyncio.to_thread(control._fila, clave)
    return await _aplicar_control(f"{control.nombre_servicio(sid)} bloqueado en «{control.nombre_de(r)}».")


@tool("desbloquear_servicio", "Quita el bloqueo de un servicio en UN dispositivo.",
      {"dispositivo": ("string", "Alias, nombre, IP o MAC del dispositivo"),
       "servicio": ("string", "Servicio a desbloquear (p. ej. tiktok)")},
      ("dispositivo", "servicio"), especialista=True)
async def desbloquear_servicio(dispositivo, servicio) -> str:
    clave = await _clave_control(dispositivo)
    sid = await asyncio.to_thread(control.desbloquear_servicio, clave, str(servicio or ""))
    r = await asyncio.to_thread(control._fila, clave)
    return await _aplicar_control(f"{control.nombre_servicio(sid)} desbloqueado en «{control.nombre_de(r)}».")


@tool("estado_control", "Estado del control parental: qué dispositivos tienen internet pausado, servicios bloqueados u "
      "horarios. Sin dispositivo, los que tienen algo activo.",
      {"dispositivo": ("string", "Alias, nombre, IP o MAC (opcional)")}, especialista=True)
async def estado_control(dispositivo=None) -> str:
    if dispositivo:
        clave = await _clave_control(dispositivo)
        return control.texto_estado((await asyncio.to_thread(control.estado, clave))[0]) + "."
    es = await asyncio.to_thread(control.estado)
    if not es:
        return "Ningún dispositivo tiene internet pausado, servicios bloqueados ni horarios."
    return f"{len(es)} dispositivo(s) con control: " + " | ".join(control.texto_estado(e) for e in es[:30]) + "."


_SERVICIOS_RE = (r"\b(tik ?tok|you ?tube|yt|insta(gram)?|face(book)?|fb|whats ?app|wasap|snap(chat)?|twitter|twitch|discord|"
                 r"fortnite|epic|roblox|minecraft|steam|netflix|disney\+?|prime( video)?)\b")
_DISPOSITIVO_RE = (r"\b(internet|wifi|wi-fi|conexi[oó]n|ipad|tablet|m[oó]vil|tel[eé]fono|port[aá]til|ordenador|pc|consola|"
                   r"switch|play ?station|ps[45]|xbox|fire ?tv|tele|tv|televisi[oó]n|dispositivo|hij[oa]s?)\b")
_INTENCIONES += [
    ((r"\b(paus\w+|cort\w+|apag\w+|quit\w+|desconect\w+|bloque\w+|sin)\b", _DISPOSITIVO_RE, r"!" + _BLOQUEADOR,
      r"!\b(desbloque\w+|reanud\w+)\b"), {"pausar_internet"}),
    ((r"\b(reanud\w+|restablec\w+|activ[ae]\w*|devuelve\w*|vuelve\w*|conect[ae]\w*|d[eé]ja\w*|quita\w* la pausa)\b",
      _DISPOSITIVO_RE, r"!" + _BLOQUEADOR), {"reanudar_internet", "estado_control"}),
    ((r"\b(bloque\w+|proh[ií]be\w*|impide\w*|quita\w*|corta\w*|sin)\b", _SERVICIOS_RE, r"!\b(desbloque\w+)\b"),
     {"bloquear_servicio"}),
    ((r"\b(desbloque\w+|permite\w*|deja\w*|vuelve\w*|quita\w* el bloqueo)\b", _SERVICIOS_RE), {"desbloquear_servicio"}),
    ((r"\b(control parental|pausad\w+|bloquead\w+|restricci\w+|sin internet|horarios?)\b", r"!" + _BLOQUEADOR),
     {"estado_control"}),
]


# --- Recordatorios (del usuario que chatea) ------------------------------------------------------------
@tool("recordatorio",
      "Programa un recordatorio para el usuario: ARIA le avisará a esa hora por Telegram, notificación y la campana. "
      "Calcula tú la fecha y hora a partir de la fecha de hoy que tienes arriba.",
      {"texto": ("string", "Qué hay que recordar, en pocas palabras (p. ej. «llamar al taller»)"),
       "cuando": ("string", "Fecha y hora LOCAL en formato ISO AAAA-MM-DDTHH:MM (p. ej. 2026-10-09T09:00). «Por la "
                            "tarde» = 17:00, «por la mañana» = 09:00, «por la noche» = 21:00. Si es recurrente, la "
                            "primera vez."),
       "repetir": ("string", "Vacío si es una sola vez; «diario», «semanal» (mismo día de la semana) o «laborables»")},
      ("texto", "cuando"), usa_uid=True)
async def recordatorio(uid, texto, cuando, repetir="") -> str:
    try:
        r = await asyncio.to_thread(recordatorios.crear, uid, texto, cuando, repetir or None)
    except recordatorios.RecordatorioError as e:
        return str(e)
    return f"Recordatorio {r['id']} programado: «{r['texto']}», {r['descripcion']}."


@tool("mis_recordatorios", "Lista los recordatorios pendientes del usuario (número, texto y cuándo).", usa_uid=True)
async def mis_recordatorios(uid) -> str:
    rs = await asyncio.to_thread(recordatorios.listar, uid)
    if not rs:
        return "No tienes recordatorios pendientes."
    return f"{len(rs)} recordatorio(s): " + "; ".join(f"{r['id']}: {r['texto']} ({r['descripcion']})" for r in rs[:30]) + "."


@tool("borrar_recordatorio", "Borra un recordatorio del usuario por su número o por unas palabras de su texto.",
      {"id_o_texto": ("string", "Número del recordatorio o palabras de su texto")}, ("id_o_texto",), usa_uid=True)
async def borrar_recordatorio(uid, id_o_texto) -> str:
    hallados = await asyncio.to_thread(recordatorios.buscar, uid, id_o_texto)
    if not hallados:
        return "No encuentro ese recordatorio."
    if len(hallados) > 1:
        return "Encajan varios: " + "; ".join(f"{r['id']}: {r['texto']}" for r in hallados[:5]) + ". Dime el número."
    await asyncio.to_thread(recordatorios.borrar, uid, hallados[0]["id"])
    return f"Recordatorio borrado: «{hallados[0]['texto']}»."


# --- Enlaces --------------------------------------------------------------------------------------------
@tool("resumir_enlace",
      "Abre una página web (http/https pública) y devuelve su título y texto para resumirla o comentarla. Úsala "
      "cuando el usuario pegue o comparta un enlace y pida un resumen, tu opinión o qué dice.",
      {"url": ("string", "La dirección completa de la página (https://…)")}, ("url",))
async def resumir_enlace(url: str) -> str:
    try:
        return await enlaces.leer(str(url))
    except enlaces.EnlaceError as e:
        return f"No he podido leer ese enlace: {e}"


# --- Rutinas (del usuario que chatea) --------------------------------------------------------------------
def _rol_de(uid: int) -> str:
    from . import usuarios
    u = usuarios.por_id(uid)
    return u["rol"] if u and u["activo"] else "ninguno"


@tool("crear_rutina",
      "Crea una rutina: una tarea que ARIA hará sola a una hora fija (p. ej. «cada mañana a las 8, dime el tiempo y "
      "3 titulares») y cuyo resultado envía por Telegram, notificación o la campana. Las rutinas solo consultan.",
      {"nombre": ("string", "Nombre corto (p. ej. «Tiempo y noticias»)"),
       "prompt": ("string", "Lo que ARIA debe hacer cada vez, como si se lo pidiera el usuario"),
       "horario": ("string", "Cuándo, en español: «todos los días a las 08:00», «de lunes a viernes a las 7:30», "
                             "«los lunes y jueves a las 9:00», «cada 3 horas» (mínimo cada hora)"),
       "canal": ("string", "telegram (por defecto), push, ambos o web (solo la campana)"),
       "agente": ("string", "aria (por defecto), finanzas, redes o seguridad")},
      ("nombre", "prompt", "horario"), usa_uid=True)
async def crear_rutina(uid, nombre, prompt, horario, canal="telegram", agente="aria") -> str:
    try:
        r = await asyncio.to_thread(rutinas.crear, uid, await asyncio.to_thread(_rol_de, uid),
                                    {"nombre": nombre, "prompt": prompt, "horario": horario,
                                     "canal": canal or "telegram", "agente": agente or "aria"})
    except rutinas.RutinaError as e:
        return str(e)
    return (f"Rutina {r['id']} creada: «{r['nombre']}», {r['descripcion']}, por {rutinas.NOMBRE_CANAL[r['canal']]}. "
            "Puedes pausarla, editarla o ejecutarla ya en Ajustes → Rutinas.")


@tool("mis_rutinas", "Lista las rutinas del usuario (número, nombre, cuándo y si están en pausa).", usa_uid=True)
async def mis_rutinas(uid) -> str:
    rs = await asyncio.to_thread(rutinas.listar, uid)
    if not rs:
        return "No tienes rutinas. Por ejemplo: «crea una rutina que cada día a las 8 me diga el tiempo»."
    return f"{len(rs)} rutina(s): " + "; ".join(
        f"{r['id']}: {r['nombre']} ({r['descripcion']}{'' if r['activa'] else ', EN PAUSA'})" for r in rs) + "."


@tool("borrar_rutina", "Borra una rutina del usuario por su número o por palabras de su nombre.",
      {"id_o_nombre": ("string", "Número de la rutina o palabras de su nombre")}, ("id_o_nombre",), usa_uid=True)
async def borrar_rutina(uid, id_o_nombre) -> str:
    hallados = await asyncio.to_thread(rutinas.buscar, uid, id_o_nombre)
    if not hallados:
        return "No encuentro esa rutina."
    if len(hallados) > 1:
        return "Encajan varias: " + "; ".join(f"{r['id']}: {r['nombre']}" for r in hallados[:5]) + ". Dime el número."
    await asyncio.to_thread(rutinas.borrar, uid, hallados[0]["id"])
    return f"Rutina borrada: «{hallados[0]['nombre']}»."


@tool("crear_automatizacion", "Propone una automatización y espera confirmación explícita antes de crearla.",
      {"nombre": ("string", "Nombre de la regla"), "disparador": ("string", "Evento, hora o umbral en lenguaje natural"),
       "accion": ("string", "Acción segura que se ejecutará")}, ("nombre", "disparador", "accion"))
async def crear_automatizacion(nombre, disparador, accion) -> str:
    return (f"Propongo la automatización «{nombre}»: cuando {disparador}, entonces {accion}. "
            "Confírmala en Ajustes → Automatizaciones o responde «confirmo» para que ARIA la cree.")


@tool("mis_automatizaciones", "Lista las automatizaciones del usuario administrador.", usa_uid=True)
async def mis_automatizaciones(uid) -> str:
    rs = await asyncio.to_thread(automatizaciones.listar, uid)
    return "No tienes automatizaciones." if not rs else "; ".join(f"{r['id']}: {r['nombre']}" for r in rs) + "."


@tool("borrar_automatizacion", "Solicita confirmación antes de borrar una automatización.",
      {"id": ("integer", "Número de la automatización")}, ("id",))
async def borrar_automatizacion(id) -> str:
    return f"Confirma en Ajustes → Automatizaciones que quieres borrar la automatización {id}."


_INTENCIONES += [
    ((r"https?://",), {"resumir_enlace"}),
    ((r"\brutinas?\b", r"\b(crea\w*|nueva|programa\w*|a[ñn]ade\w*|haz\w*|hazme|pon\w*|configura\w*)\b",
      r"!\b(borra\w*|quita\w*|elimina\w*)\b"), {"crear_rutina"}),
    ((r"\brutinas?\b", r"\b(mis|qu[eé]|cu[aá]les|tengo|lista\w*|ver)\b", r"!\b(crea\w*|nueva)\b"), {"mis_rutinas"}),
    ((r"\brutinas?\b", r"\b(borra\w*|quita\w*|elimina\w*|cancela\w*)\b"), {"borrar_rutina", "mis_rutinas"}),
    ((r"\b(automatizaci[oó]n|regla)\b", r"\b(crea\w*|programa\w*|cuando|si)\b"), {"crear_automatizacion"}),
    ((r"\b(automatizaciones?|reglas)\b", r"\b(mis|lista\w*|cu[aá]les|ver)\b"), {"mis_automatizaciones"}),
    ((r"\b(automatizaci[oó]n|regla)\b", r"\b(borra\w*|elimina\w*|quita\w*)\b"), {"borrar_automatizacion", "mis_automatizaciones"}),
]


# --- Herramientas de módulos (modulos.py / sdk.py) ---------------------------------------------------------------
# Nombres del núcleo (incluidas las aparcadas): ningún módulo puede usarlos.
NUCLEO = frozenset(_REGISTRO)
_DE_MODULOS: dict = {}   # nombre -> {"modulo", "usuario", "solo_lectura", "agentes", "entradas"}


def registrar_externa(nombre: str, fn, descripcion: str, params: dict, requeridos: tuple, *, modulo: str,
                      solo_lectura: bool, usuario: bool, intenciones: list, agentes: tuple) -> None:
    """Herramienta de un módulo. Ya viene validada por el SDK; aquí solo se comprueba el choque de nombres.
    `solo_lectura` la deja usar en las rutinas; `usuario` la abre al rol `usuario`; `agentes` dice qué agentes
    la ofrecen (sin «aria» es de especialista); `intenciones` son las entradas del filtro de `relevantes`."""
    global RUTINAS
    if nombre in NUCLEO or nombre in _REGISTRO:
        raise ValueError(f"la herramienta «{nombre}» ya existe")
    tool(nombre, descripcion, params, tuple(requeridos), especialista="aria" not in agentes)(fn)
    entradas = [(tuple(p), {nombre}) for p in intenciones]
    _INTENCIONES.extend(entradas)
    _DE_MODULOS[nombre] = {"modulo": modulo, "usuario": usuario, "solo_lectura": solo_lectura,
                           "agentes": frozenset(agentes), "entradas": entradas}
    if solo_lectura:
        RUTINAS = RUTINAS | {nombre}


def retirar_externa(nombre: str) -> None:
    global RUTINAS
    info = _DE_MODULOS.pop(nombre, None)
    if info is None:
        return
    _REGISTRO.pop(nombre, None)
    _INTENCIONES[:] = [e for e in _INTENCIONES if not any(e is x for x in info["entradas"])]
    RUTINAS = RUTINAS - {nombre}


def de_modulos(agente: str) -> set:
    """Herramientas de módulos que ofrece ese agente."""
    return {n for n, i in _DE_MODULOS.items() if agente in i["agentes"]}


# Spotify y Netflix quedan aparcados salvo ARIA_SPOTIFY=1 / ARIA_NETFLIX=1 (ver config.py).
for _n in [n for n in _REGISTRO if (n.startswith("spotify_") and not config.SPOTIFY)
           or (n == "buscar_en_netflix" and not config.NETFLIX)]:
    del _REGISTRO[_n]
