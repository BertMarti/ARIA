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

from . import config, escaneo, finanzas, red, seguridad, services, shield, sistema, spotify, vpn

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
                          "estado_sistema", "buscar_en_netflix"})


# Además, el rol `usuario` puede usar sus finanzas (solo sus datos) y la salud de la red (solo lectura).
DE_USUARIO = frozenset({"registrar_movimiento", "resumen_mes", "gastos_por_categoria", "comparar_meses",
                        "presupuesto", "estado_presupuestos", "buscar_movimientos", "estado_red"})


def permitidas(rol: str) -> set:
    """Nombres de herramientas que ese rol puede ver y ejecutar."""
    if rol == "admin":
        return set(_REGISTRO)
    if rol == "usuario":
        return set(SOLO_LECTURA | DE_USUARIO) & set(_REGISTRO)
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


_ERRORES_LEGIBLES = (spotify.SpotifyError, shield.ShieldError, vpn.VpnError, finanzas.FinanzasError,
                     red.RedError, escaneo.EscaneoError)


def registrar_errores(*clases) -> None:
    """Otros módulos añaden sus excepciones «legibles» (mensaje en español para el modelo)."""
    global _ERRORES_LEGIBLES
    _ERRORES_LEGIBLES = tuple(dict.fromkeys(_ERRORES_LEGIBLES + clases))


async def ejecutar(nombre: str, args: dict | None, rol: str = "admin", uid: int | None = None,
                   solo: set | None = None) -> str:
    """Ejecuta una herramienta comprobando el rol y, si se da `solo`, las del agente activo."""
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


@tool("escanear_red", "Pide un escaneo de puertos (nmap) de la red de casa 192.168.0.0/24. Como mucho uno cada 10 minutos.",
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

# Palabras clave para el cerebro local (los de la nube reciben todas las del agente).
_INTENCIONES += [
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
