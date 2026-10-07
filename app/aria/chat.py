"""Bucle de chat: cerebro -> llamadas a herramientas -> resultados -> cerebro."""
import json
from typing import AsyncIterator

from . import cerebros, db, tools

MAX_RONDAS = 5
MAX_MENSAJES = 40
MAX_CHARS = 8000

def limpiar(mensajes) -> list:
    out = []
    for m in (mensajes or [])[-MAX_MENSAJES:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            out.append({"role": m["role"], "content": m["content"][:MAX_CHARS]})
    return out


async def responder(mensajes: list, rol: str = "admin", quien: str | None = None) -> AsyncIterator[dict]:
    """Genera eventos: cerebro, pensando, token, herramienta, resultado, aviso, reinicio, error, fin.

    En cada ronda se prueba la cadena de cerebros en orden; si uno falla se pasa al siguiente.
    """
    msgs = limpiar(mensajes)
    ultimo_error = None
    for _ in range(MAX_RONDAS):
        llamadas, texto, hecha = [], "", False
        for prov in cerebros.cadena():
            enviados, anunciado = False, False
            try:
                async for ev in prov.ronda(msgs, rol=rol, nombre=quien):
                    if ev["type"] in ("token", "pensando", "llamadas") and not anunciado:
                        anunciado = True
                        yield {"type": "cerebro", "id": prov.id, "nombre": prov.nombre,
                               "modelo": prov.modelo(), "etiqueta": prov.etiqueta()}
                    if ev["type"] == "llamadas":
                        llamadas, texto = ev["llamadas"], ev.get("texto", "")
                    else:
                        enviados = enviados or ev["type"] == "token"
                        yield ev
                hecha = True
                break
            except cerebros.ProveedorError as e:
                ultimo_error = e
                if prov.id != "local":
                    cerebros.registrar_fallo(prov.id, e)
                if enviados:
                    yield {"type": "aviso", "text": f"{prov.nombre} se interrumpió; sigo con otro cerebro."}
                    yield {"type": "reinicio"}
        if not hecha:
            msg = ultimo_error.mensaje if ultimo_error and ultimo_error.tipo == "modelo" else \
                "No hay ningún cerebro disponible ahora mismo."
            yield {"type": "error", "text": msg}
            return
        if not llamadas:
            yield {"type": "fin"}
            return
        msgs.append({"role": "assistant", "content": texto, "tool_calls": llamadas})
        for ll in llamadas:
            f = ll.get("function", {})
            nombre, args = f.get("name", ""), f.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            yield {"type": "herramienta", "name": nombre, "args": args}
            res = await tools.ejecutar(nombre, args, rol)
            yield {"type": "resultado", "name": nombre, "text": res[:2000]}
            msgs.append({"role": "tool", "tool_name": nombre, "content": res})
    yield {"type": "error", "text": "Demasiadas llamadas a herramientas seguidas."}


async def conversar(usuario: dict, cid: str | None, texto: str) -> AsyncIterator[dict]:
    """Guarda el mensaje, responde en streaming y persiste la respuesta (aunque se aborte).

    La conversación debe ser del usuario; si no lo es (o no existe) se crea una nueva."""
    texto = texto.strip()[:MAX_CHARS]
    uid = usuario["id"]
    if not cid or not db.existe(cid, uid):
        cid = db.crear(uid)
    if db.es_primer_mensaje(cid):
        db.renombrar(cid, uid, db.titulo_desde(texto))
    db.anadir(cid, "user", texto)
    conv = db.obtener(cid, uid)
    yield {"type": "conv", "id": cid, "titulo": conv["titulo"]}
    contexto = db.historial_modelo(cid, MAX_MENSAJES)
    acumulado, pendiente, cerebro = "", None, None
    try:
        async for ev in responder(contexto, usuario["rol"], usuario["nombre"]):
            if ev["type"] == "cerebro":
                cerebro = ev["etiqueta"]
            elif ev["type"] == "token":
                acumulado += ev["text"]
            elif ev["type"] == "reinicio":
                acumulado = ""
            elif ev["type"] == "herramienta":
                if acumulado.strip():
                    db.anadir(cid, "assistant", acumulado, cerebro)
                acumulado = ""
                pendiente = (ev["name"], ev["args"])
            elif ev["type"] == "resultado":
                db.anadir(cid, "tool", db.herramienta_json(ev["name"], pendiente[1] if pendiente else {}, ev["text"]))
            yield ev
    finally:
        # También se ejecuta si el cliente aborta (botón Detener): se conserva lo generado.
        if acumulado.strip():
            db.anadir(cid, "assistant", acumulado, cerebro)
