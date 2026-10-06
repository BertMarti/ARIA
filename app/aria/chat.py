"""Bucle de chat con Ollama: modelo -> llamadas a herramientas -> resultados -> modelo."""
import json
from typing import AsyncIterator

import httpx

from . import config, db, tools

MAX_RONDAS = 5
MAX_MENSAJES = 40
MAX_CHARS = 8000

# Modelos que han rechazado tools (se recuerda para no reintentar).
_sin_tools: set = set()


def limpiar(mensajes) -> list:
    out = []
    for m in (mensajes or [])[-MAX_MENSAJES:]:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            out.append({"role": m["role"], "content": m["content"][:MAX_CHARS]})
    return out


async def _stream_ollama(cliente: httpx.AsyncClient, msgs: list, nombres_tools: set):
    cuerpo = {
        "model": config.modelo_activo(),
        "messages": msgs,
        "stream": True,
        "keep_alive": config.KEEP_ALIVE,
        "options": {"num_ctx": config.NUM_CTX},
    }
    if nombres_tools:
        cuerpo["tools"] = tools.especificaciones(nombres_tools)
    async with cliente.stream("POST", f"{config.OLLAMA_URL}/api/chat", json=cuerpo) as r:
        if r.status_code != 200:
            texto = (await r.aread()).decode("utf-8", "replace")
            yield {"_http": r.status_code, "_texto": texto}
            return
        async for linea in r.aiter_lines():
            if linea.strip():
                yield json.loads(linea)


async def responder(mensajes: list) -> AsyncIterator[dict]:
    """Genera eventos: token, herramienta, resultado, error, fin."""
    msgs = [{"role": "system", "content": config.SYSTEM_PROMPT}] + limpiar(mensajes)
    modelo = config.modelo_activo()
    pedidas = tools.relevantes(msgs[-1]["content"])
    timeout = httpx.Timeout(600, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as cliente:
        try:
            for _ in range(MAX_RONDAS):
                usar_tools = modelo not in _sin_tools and bool(pedidas)
                texto, llamadas, fallo = "", [], None
                for intento in (0, 1):
                    texto, llamadas, fallo = "", [], None
                    modo = None  # "texto" se emite en directo; "json" se retiene por si es una llamada
                    async for ch in _stream_ollama(cliente, msgs, pedidas if usar_tools else set()):
                        if "_http" in ch:
                            fallo = ch
                            break
                        m = ch.get("message") or {}
                        if m.get("content"):
                            texto += m["content"]
                            if modo is None and texto.strip():
                                modo = "json" if usar_tools and texto.lstrip()[0] == "{" else "texto"
                                if modo == "texto":
                                    yield {"type": "token", "text": texto}
                            elif modo == "texto":
                                yield {"type": "token", "text": m["content"]}
                        llamadas += m.get("tool_calls") or []
                    if not fallo and not llamadas and modo == "json":
                        rescatada = tools.rescatar_llamada(texto, pedidas)
                        if rescatada:
                            llamadas, texto = [rescatada], ""
                        else:
                            yield {"type": "token", "text": texto}
                    if fallo and fallo["_http"] == 400 and "tools" in fallo["_texto"] and usar_tools:
                        _sin_tools.add(modelo)
                        usar_tools = False
                        yield {"type": "aviso", "text": "Este modelo no admite herramientas; respondo sin ellas."}
                        continue
                    break
                if fallo:
                    if fallo["_http"] == 404:
                        yield {"type": "error", "text": f"El modelo '{modelo}' no está instalado. Descárgalo en Ajustes → Modelos."}
                    else:
                        yield {"type": "error", "text": f"Ollama devolvió un error ({fallo['_http']})."}
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
                    res = await tools.ejecutar(nombre, args)
                    yield {"type": "resultado", "name": nombre, "text": res[:2000]}
                    msgs.append({"role": "tool", "tool_name": nombre, "content": res})
            yield {"type": "error", "text": "Demasiadas llamadas a herramientas seguidas."}
        except httpx.HTTPError:
            yield {"type": "error", "text": "No se pudo contactar con Ollama."}


async def conversar(cid: str | None, texto: str) -> AsyncIterator[dict]:
    """Guarda el mensaje, responde en streaming y persiste la respuesta (aunque se aborte)."""
    texto = texto.strip()[:MAX_CHARS]
    if not cid or not db.existe(cid):
        cid = db.crear()
    if db.es_primer_mensaje(cid):
        db.renombrar(cid, db.titulo_desde(texto))
    db.anadir(cid, "user", texto)
    conv = db.obtener(cid)
    yield {"type": "conv", "id": cid, "titulo": conv["titulo"]}
    contexto = db.historial_modelo(cid, MAX_MENSAJES)
    acumulado, pendiente = "", None
    try:
        async for ev in responder(contexto):
            if ev["type"] == "token":
                acumulado += ev["text"]
            elif ev["type"] == "herramienta":
                if acumulado.strip():
                    db.anadir(cid, "assistant", acumulado)
                acumulado = ""
                pendiente = (ev["name"], ev["args"])
            elif ev["type"] == "resultado":
                db.anadir(cid, "tool", db.herramienta_json(ev["name"], pendiente[1] if pendiente else {}, ev["text"]))
            yield ev
    finally:
        # También se ejecuta si el cliente aborta (botón Detener): se conserva lo generado.
        if acumulado.strip():
            db.anadir(cid, "assistant", acumulado)
