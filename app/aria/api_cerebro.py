"""Mapa de la arquitectura interna de ARIA, reservado al administrador."""
import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, Query, Request

from . import agentes, briefing, cerebros, config, memoria, modulos, notas, push, registro, telegram, telemetria, tools, usuarios

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


def _nodo(nodos, ident, nombre, grupo, estado="ok", detalle="", datos=None):
    nodos.append({"id": ident, "nombre": str(nombre), "grupo": grupo, "estado": estado if estado in ("ok", "aviso", "mal", "apagado") else "mal",
                  "detalle": str(detalle)[:180], "datos": datos or {}})


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


@router.get("/api/cerebro")
async def cerebro(request: Request):
    return await _mapa(request)


@router.get("/api/cerebro/actividad")
async def actividad(request: Request, desde: float = Query(0)):
    try:
        rows = registro.listar(limite=500)
        return {"actividad": [{k: r.get(k) for k in ("ts", "herramienta", "agente", "origen", "ok")} for r in rows if r.get("ts", 0) > desde][:50]}
    except Exception:  # noqa: BLE001
        return {"actividad": []}
