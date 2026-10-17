"""Mapa de la arquitectura interna de ARIA, reservado al administrador."""
import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request

from . import agentes, briefing, cerebros, config, memoria, modulos, notas, premium, push, registro, telegram, telemetria, tools, usuarios

router = APIRouter()

_FAMILIAS = {
    "memoria": ("memoria", "recuerdo", "diario", "aprender", "personalidad"),
    "notas": ("nota", "proyecto", "decision"),
    "agenda": ("agenda", "evento", "cumple", "recordatorio", "rutina"),
    "red": ("red", "dispositivo", "latencia", "velocidad", "vpn", "bloqueador"),
    "seguridad": ("seguridad", "escaneo", "cve", "bloqueo"),
    "finanzas": ("gasto", "ingreso", "presupuesto", "movimiento", "mes", "categoria"),
    "información": ("buscar", "noticia", "mercado", "enlace", "informacion", "resumir"),
    "voz/espacio": ("voz", "hablar", "transcribir", "spotify"),
    "sistema": ("sistema", "servicio", "hora", "luz", "clima", "reiniciar"),
    "módulos": ("modulo",),
}

_QUE_HACE = {
    "núcleo": "Coordina ARIA, sus datos y las tareas que mantienen el laboratorio disponible.",
    "cerebros": "Procesa las conversaciones y elige el proveedor de IA disponible para cada respuesta.",
    "agentes": "Agrupa las capacidades de ARIA por oficio para responder con herramientas adecuadas.",
    "herramientas": "Reúne herramientas relacionadas y muestra cuánto se han utilizado recientemente.",
    "módulos": "Añade extensiones opcionales a ARIA sin mezclar su código con el núcleo.",
    "servicios": "Es un servicio que ARIA necesita para ofrecer una parte de sus funciones.",
    "canales": "Permite recibir avisos o conversar con ARIA desde ese medio.",
    "datos": "Guarda o consulta información de ARIA respetando el usuario que la solicita.",
    "túnel": "Conecta de forma segura con la red privada para acceder a servicios autorizados.",
    "copias": "Resume el estado de las copias de seguridad de los datos de ARIA.",
}

_QUE_HACE_ID = {
    "aria": "Es el núcleo de ARIA: coordina conversaciones, agentes, herramientas y avisos.",
    "servicio-aria-voz": "Transcribe audio y prepara la respuesta hablada para la interacción por voz.",
    "servicio-ollama": "Ofrece inferencia local cuando se configura un modelo compatible.",
    "servicio-searxng": "Busca información en Internet sin exponer directamente el navegador de ARIA.",
    "shield-dns": "Filtra consultas DNS y ayuda a proteger y ordenar la red doméstica.",
    "heimdall": "Proporciona el túnel privado para acceder a la red doméstica de forma segura.",
    "canal-telegram": "Envía avisos y permite consultar ARIA desde Telegram.",
    "canal-push": "Entrega avisos del navegador en los dispositivos que el usuario ha vinculado.",
    "canal-web": "Es la interfaz web para conversar, consultar datos y administrar ARIA.",
    "datos-memoria": "Conserva recuerdos autorizados para personalizar futuras conversaciones.",
    "datos-notas": "Organiza notas y decisiones que el usuario quiere conservar.",
    "datos-db": "Almacena el estado estructurado de ARIA y sus registros internos.",
    "tunel": "Mantiene la conexión privada disponible para los servicios que la necesitan.",
    "copias": "Comprueba cuándo se hizo la última copia de seguridad conocida.",
}


def _contenido(ident, nombre, grupo, estado, datos):
    """Genera texto útil sin incluir valores de configuración ni datos privados."""
    clave = ident.lower()
    que_hace = _QUE_HACE_ID.get(clave)
    if not que_hace:
        que_hace = next((texto for clave_id, texto in _QUE_HACE_ID.items() if clave_id in clave or clave_id in nombre.lower()), None)
    que_hace = que_hace or _QUE_HACE.get(grupo, "Forma parte de la arquitectura de ARIA.")
    mejoras = []
    if estado == "mal" and grupo == "cerebros":
        mejoras.append("Revisa la clave o el cupo en Ajustes → Cerebros.")
    elif estado == "mal" and grupo == "servicios":
        mejoras.append("Comprueba el servicio desde Centro de control y reinícialo si procede.")
    elif estado == "mal":
        mejoras.append("Consulta el detalle y revisa la configuración de esta capacidad.")
    if grupo == "herramientas" and not datos.get("usos"):
        mejoras.append("Prueba una herramienta de esta familia en el chat con una petición sencilla.")
    if grupo == "copias" and estado in ("aviso", "apagado", "mal"):
        mejoras.append("Lanza una copia y comprueba su estado desde Telegram con /copia.")
    if not mejoras:
        ideas = {
            "cerebros": "Usa este cerebro para comparar respuestas y repartir la carga.",
            "agentes": "Pídele una tarea de su especialidad desde el chat para aprovechar sus herramientas.",
            "herramientas": "Consulta esta familia en el chat cuando necesites datos actualizados.",
            "servicios": "Revisa periódicamente su estado para detectar cortes antes de que afecten al chat.",
            "canales": "Activa avisos en este canal para recibir información importante a tiempo.",
            "datos": "Mantén solo la información útil y revisa periódicamente sus registros.",
            "módulos": "Activa únicamente las extensiones que aporten una función que uses.",
            "copias": "Comprueba con regularidad que la última copia sigue siendo reciente.",
        }
        mejoras.append(ideas.get(grupo, "Revisa este nodo desde el mapa cuando quieras comprobar su estado."))
    return que_hace, mejoras[:3]


def _nodo(nodos, ident, nombre, grupo, estado="ok", detalle="", datos=None):
    datos = datos or {}
    estado = estado if estado in ("ok", "aviso", "mal", "apagado") else "mal"
    que_hace, mejoras = _contenido(ident, nombre, grupo, estado, datos)
    nodos.append({"id": ident, "nombre": str(nombre), "grupo": grupo, "estado": estado,
                  "detalle": str(detalle)[:180], "datos": datos, "que_hace": que_hace,
                  "mejoras": mejoras})


def _familia(nombre):
    n = nombre.lower()
    for familia, palabras in _FAMILIAS.items():
        if any(p in n for p in palabras):
            return familia
    return "sistema"


def _seguro(nodos, fn, ident, nombre, grupo, datos=None):
    try:
        estado, detalle, extra = fn()
        _nodo(nodos, ident, nombre, grupo, estado, detalle, {**(datos or {}), **(extra or {})})
    except Exception:  # noqa: BLE001 - el mapa nunca debe impedir el acceso al panel
        _nodo(nodos, ident, nombre, grupo, "mal", "sin datos", datos)


async def _mapa(request: Request):
    nodos, enlaces = [], []
    _seguro(nodos, lambda: ("ok", "núcleo operativo", {"versión": config.VERSION, "usuarios activos": sum(1 for u in usuarios.listar() if u.get("activo"))}),
            "aria", "ARIA", "núcleo")

    def cerebros_fuente():
        datos = cerebros.estado()
        return datos
    try:
        for c in cerebros_fuente():
            estado = "ok" if c.get("estado") == "configurado" and c.get("activo") else ("apagado" if not c.get("activo") else "aviso")
            ident = "cerebro-" + c["id"]
            _nodo(nodos, ident, c.get("nombre", c["id"]), "cerebros", estado, c.get("modelo", c.get("detalle", "")), {"modelo": c.get("modelo", ""), "estado": c.get("estado", "")})
            enlaces.append({"origen": "aria", "destino": ident})
    except Exception:  # noqa: BLE001
        _nodo(nodos, "cerebros-sin-datos", "Cerebros", "cerebros", "mal", "sin datos")
        enlaces.append({"origen": "aria", "destino": "cerebros-sin-datos"})

    familias = {}
    try:
        usos = registro.listar(limite=500)
        recientes = [r for r in usos if r.get("ts", 0) >= time.time() - 86400]
        for nombre in tools._REGISTRO:
            familias.setdefault(_familia(nombre), {"total": 0, "usos": 0})["total"] += 1
        for r in recientes:
            familias.setdefault(_familia(r.get("herramienta", "")), {"total": 0, "usos": 0})["usos"] += 1
    except Exception:  # noqa: BLE001
        familias = {f: {"total": 0, "usos": 0, "error": True} for f in _FAMILIAS}
    for familia, d in familias.items():
        ident = "herramientas-" + familia.replace("/", "-")
        _nodo(nodos, ident, familia.capitalize(), "herramientas", "mal" if d.pop("error", False) else "ok", f'{d["total"]} herramientas', d)
    for a in agentes.AGENTES.values():
        try:
            hs = agentes.herramientas(a, "admin")
            ident = "agente-" + a.id
            _nodo(nodos, ident, "Agente " + a.nombre if a.nombre == "ARIA" else a.nombre, "agentes", "ok", f"{len(hs)} herramientas", {"herramientas": len(hs)})
            enlaces.append({"origen": "aria", "destino": ident})
            for familia in {_familia(h) for h in hs}:
                destino = "herramientas-" + familia.replace("/", "-")
                if any(n["id"] == destino for n in nodos): enlaces.append({"origen": ident, "destino": destino})
        except Exception:  # noqa: BLE001
            _nodo(nodos, "agente-" + a.id, a.nombre, "agentes", "mal", "sin datos")

    try:
        for m in await modulos.listar("admin"):
            estado = {"activo": "ok", "sin_configurar": "aviso", "error": "mal"}.get(m.get("estado"), "apagado")
            ident = "modulo-" + m["id"]
            _nodo(nodos, ident, m.get("nombre", m["id"]), "módulos", estado, m.get("estado", ""), {"versión": m.get("version", ""), "salud": m.get("salud")})
    except Exception: _nodo(nodos, "modulos-sin-datos", "Módulos", "módulos", "mal", "sin datos")

    try:
        directo = telemetria.directo()
        for c in directo.get("contenedores", []):
            _nodo(nodos, "servicio-" + str(c.get("nombre", "servicio")), c.get("nombre", "Servicio"), "servicios", "ok", "en ejecución", {"CPU %": c.get("cpu", 0), "memoria": c.get("memoria", 0)})
    except Exception: _nodo(nodos, "servicios-sin-datos", "Servicios", "servicios", "mal", "sin datos")
    for ident, nombre in (("servicio-aria-voz", "aria-voz"), ("servicio-ollama", "Ollama"), ("servicio-searxng", "SearXNG")):
        if not any(n["id"] == ident for n in nodos): _nodo(nodos, ident, nombre, "servicios", "apagado", "sin telemetría")

    def fuente(ident, nombre, grupo, estado, detalle, datos=None): _nodo(nodos, ident, nombre, grupo, estado, detalle, datos)
    try: fuente("canal-telegram", "Telegram", "canales", "ok" if telegram.configurado() else "apagado", "configurado" if telegram.configurado() else "sin configurar", {"vinculados": sum(len(telegram.chats_de(u["id"])) for u in usuarios.listar())})
    except Exception: fuente("canal-telegram", "Telegram", "canales", "mal", "sin datos")
    try: fuente("canal-push", "Push", "canales", "ok", "disponible", {"vinculados": len(push.listar(request.state.usuario["id"]))})
    except Exception: fuente("canal-push", "Push", "canales", "mal", "sin datos")
    fuente("canal-web", "Web", "canales", "ok", "disponible")
    try: fuente("datos-db", "Base de datos", "datos", "ok", "SQLite", {"tamaño": Path(config.DATA_DIR / "aria.db").stat().st_size})
    except Exception: fuente("datos-db", "Base de datos", "datos", "mal", "sin datos")
    for ident, nombre, fn in (("datos-memoria", "Memoria", lambda: len(memoria.listar(request.state.usuario["id"]))), ("datos-notas", "Notas", lambda: len(notas.listar(request.state.usuario["id"])) )):
        _seguro(nodos, lambda fn=fn: ("ok", "registros", {"cantidad": fn()}), ident, nombre, "datos")
    _seguro(nodos, lambda: (("ok", "conectado", telemetria.estado_tunel() or {}) if telemetria.estado_tunel() else ("apagado", "sin datos", {})), "tunel", "Túnel", "túnel")
    _seguro(nodos, lambda: ("ok", "última copia", briefing.ultima_copia()), "copias", "Copias", "copias")
    ids = {n["id"] for n in nodos}
    enlaces = [e for e in enlaces if e["origen"] in ids and e["destino"] in ids]
    return {"nodos": nodos, "enlaces": enlaces, "generado": time.time()}


@router.get("/api/cerebro", dependencies=[Depends(premium.requiere("cerebro"))])
async def cerebro(request: Request):
    return await _mapa(request)


@router.get("/api/cerebro/actividad", dependencies=[Depends(premium.requiere("cerebro"))])
async def actividad(request: Request, desde: float = Query(0)):
    try:
        rows = registro.listar(limite=500)
        return {"actividad": [{k: r.get(k) for k in ("ts", "herramienta", "agente", "origen", "ok")} for r in rows if r.get("ts", 0) > desde][:50]}
    except Exception:  # noqa: BLE001
        return {"actividad": []}
