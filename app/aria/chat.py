"""Bucle de chat: cerebro -> llamadas a herramientas -> resultados -> cerebro."""
import asyncio
import json
import logging
from typing import AsyncIterator

from . import aprender, briefing, cerebros, db, memoria, tools

log = logging.getLogger("aria.chat")

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
    uid, ctx = memoria.uid_actual.get(), {}

    def memoria_para(prov) -> dict:
        """Recuerdos del usuario para el prompt (nube: ~1 200 + ~900 caracteres; local: ≤ 300). Nunca rompe el chat."""
        if uid is None:
            return {}
        if prov.nube not in ctx:
            try:
                ultimo = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
                ctx[prov.nube] = memoria.contexto(uid, quien or "", ultimo, bool(prov.nube))
            except Exception:  # noqa: BLE001
                log.exception("No se pudo preparar la memoria")
                ctx[prov.nube] = ""
        return {"extra": ctx[prov.nube]} if ctx[prov.nube] else {}

    for _ in range(MAX_RONDAS):
        llamadas, texto, hecha = [], "", False
        for prov in cerebros.cadena():
            enviados, anunciado = False, False
            try:
                async for ev in prov.ronda(msgs, rol=rol, nombre=quien, **memoria_para(prov)):
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
    memoria.uid_actual.set(uid)  # las herramientas de memoria y el contexto actúan sobre este usuario
    # Primer «hola» del día: en lugar de una respuesta normal, el resumen de buenos días (versión hablada).
    if briefing.es_saludo(texto) and not await asyncio.to_thread(briefing.saludado_hoy, uid):
        try:
            hablado = briefing.texto_hablado(await briefing.obtener(usuario))
        except Exception:  # noqa: BLE001 - si falla, se responde como siempre
            log.exception("No se pudo preparar el resumen de buenos días")
            hablado = None
        if hablado:
            etiqueta = "Resumen de buenos días"
            db.anadir(cid, "assistant", hablado, etiqueta)
            await asyncio.to_thread(briefing.marcar_saludado, uid)
            yield {"type": "cerebro", "id": "briefing", "nombre": "ARIA", "modelo": "resumen", "etiqueta": etiqueta}
            yield {"type": "token", "text": hablado}
            yield {"type": "fin"}
            return
    contexto = db.historial_modelo(cid, MAX_MENSAJES)
    acumulado, pendiente, cerebro, toco_memoria = "", None, None, False
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
                toco_memoria = toco_memoria or ev["name"] in tools.MEMORIA
            elif ev["type"] == "resultado":
                db.anadir(cid, "tool", db.herramienta_json(ev["name"], pendiente[1] if pendiente else {}, ev["text"]))
            yield ev
    finally:
        # También se ejecuta si el cliente aborta (botón Detener): se conserva lo generado.
        if acumulado.strip():
            db.anadir(cid, "assistant", acumulado, cerebro)
        # Aprendizaje automático: en segundo plano y solo con cerebros de la nube. No se aprende de peticiones
        # de recordar/olvidar (ya las atiende la herramienta; «olvida X» no debe volver a aprenderse).
        if not toco_memoria and not (tools.relevantes(texto) & tools.MEMORIA):
            try:
                aprender.programar(uid, usuario["nombre"], texto)
            except Exception:  # noqa: BLE001
                log.exception("No se pudo programar el aprendizaje")
