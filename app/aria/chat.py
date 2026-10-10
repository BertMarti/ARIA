"""Bucle de chat: cerebro -> llamadas a herramientas -> resultados -> cerebro."""
import asyncio
import json
import logging
from typing import AsyncIterator

from . import agentes, aprender, briefing, cerebros, db, invitados, memoria, tools, vision

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


async def responder(mensajes: list, rol: str = "admin", quien: str | None = None,
                    agente: "agentes.Agente | None" = None, uid: int | None = None, solo_nube: bool = False,
                    limite: "set | frozenset | None" = None) -> AsyncIterator[dict]:
    """Genera eventos: cerebro, pensando, token, herramienta, resultado, aviso, reinicio, error, fin.

    En cada ronda se prueba la cadena de cerebros en orden; si uno falla se pasa al siguiente.
    Con `agente`, se usan su prompt, sus herramientas (cruzadas con las del rol) y su cerebro preferido.
    `solo_nube` quita el cerebro local de la cadena y `limite` recorta aún más las herramientas (rutinas:
    solo las de consulta); `tools.ejecutar` vuelve a comprobarlo con `solo`.
    """
    msgs = limpiar(mensajes)
    ultimo_error = None
    permitidas = agentes.herramientas(agente, rol) if agente else None
    if limite is not None:
        permitidas = (permitidas if permitidas is not None else tools.generales() & tools.permitidas(rol)) & set(limite)
    uid, ctx = (uid if uid is not None else memoria.uid_actual.get()), {}

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

    for n_ronda in range(MAX_RONDAS):
        ultima = n_ronda == MAX_RONDAS - 1  # la última ronda va sin herramientas: obliga a responder
        llamadas, texto, hecha = [], "", False
        cadena = cerebros.cadena()
        if agente:
            cadena = cerebros.con_preferido(cadena, agente.cerebro)
        if solo_nube:
            cadena = [p for p in cadena if p.nube]
        for prov in cadena:
            enviados, anunciado = False, False
            de_agente = {}
            if agente:
                de_agente = {"herramientas": permitidas,
                         "sistema": agentes.prompt(agente, prov.nube, quien, rol == "admin")}
            elif permitidas is not None:
                de_agente = {"herramientas": permitidas}
            try:
                async for ev in prov.ronda(msgs, con_tools=not ultima, rol=rol, nombre=quien,
                                           **de_agente, **memoria_para(prov)):
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
            res = await tools.ejecutar(nombre, args, rol, uid=uid, solo=permitidas, agente=agente.id if agente else None)
            yield {"type": "resultado", "name": nombre, "text": res[:2000]}
            msgs.append({"role": "tool", "tool_name": nombre, "content": res})
    yield {"type": "error", "text": "Demasiadas llamadas a herramientas seguidas."}


async def elegir_agente(usuario: dict, conv_agente: str | None, texto: str) -> tuple:
    """(agente, texto_sin_prefijo, motivo, aviso). Aplica el prefijo @agente, el de la conversación
    o el enrutado automático de ARIA. Nunca devuelve un agente que el rol no pueda usar."""
    rol = usuario["rol"]
    pedido, limpio = agentes.separar_prefijo(texto)
    aviso = None
    if pedido:
        if agentes.permitido(pedido, rol):
            return agentes.obtener(pedido), limpio, "elegido con @", None
        aviso = f"El agente «{agentes.obtener(pedido).nombre}» es solo para administradores; te responde ARIA."
        return agentes.obtener(agentes.AUTO), limpio, "sin permiso", aviso
    if conv_agente and conv_agente != agentes.AUTO and agentes.permitido(conv_agente, rol):
        return agentes.obtener(conv_agente), texto, "elegido en la conversación", None
    aid, motivo = await agentes.enrutar(texto, rol)
    return agentes.obtener(aid), texto, motivo, None


async def conversar(usuario: dict, cid: str | None, texto: str, agente: str | None = None,
                    limites: dict | None = None) -> AsyncIterator[dict]:
    """Guarda el mensaje, responde en streaming y persiste la respuesta (aunque se aborte).

    `limites` (invitados): recorta las herramientas a consultas sin datos de casa y, si su acceso no incluye
    memoria, no aprende nada de lo que dice.

    La conversación debe ser del usuario; si no lo es (o no existe) se crea una nueva.
    `agente`: el del selector (se guarda en la conversación si el rol puede usarlo)."""
    texto = texto.strip()[:MAX_CHARS]
    uid = usuario["id"]
    if not cid or not db.existe(cid, uid):
        cid = db.crear(uid)
    if agente is not None and (agente == agentes.AUTO or agentes.permitido(agente, usuario["rol"])):
        db.fijar_agente(cid, uid, agente)
    if db.es_primer_mensaje(cid):
        db.renombrar(cid, uid, db.titulo_desde(texto))
    db.anadir(cid, "user", texto)
    conv = db.obtener(cid, uid)
    yield {"type": "conv", "id": cid, "titulo": conv["titulo"], "agente": conv.get("agente") or agentes.AUTO}
    memoria.uid_actual.set(uid)  # las herramientas de memoria y el contexto actúan sobre este usuario
    # Primer «hola» del día: en lugar de una respuesta normal, el resumen de buenos días (versión hablada).
    # (Los invitados no: ese resumen cuenta cosas de la casa.)
    if not limites and briefing.es_saludo(texto) and not await asyncio.to_thread(briefing.saludado_hoy, uid):
        try:
            hablado = briefing.texto_hablado(await briefing.obtener(usuario))
        except Exception:  # noqa: BLE001 - si falla, se responde como siempre
            log.exception("No se pudo preparar el resumen de buenos días")
            hablado = None
        if hablado:
            etiqueta = "Resumen de buenos días"
            db.anadir(cid, "assistant", hablado, etiqueta, agentes.AUTO)
            await asyncio.to_thread(briefing.marcar_saludado, uid)
            yield {"type": "agente", **agentes.obtener(agentes.AUTO).publico(), "motivo": "resumen"}
            yield {"type": "cerebro", "id": "briefing", "nombre": "ARIA", "modelo": "resumen", "etiqueta": etiqueta}
            yield {"type": "token", "text": hablado}
            yield {"type": "fin"}
            return
    ag, limpio, motivo, aviso = await elegir_agente(usuario, conv.get("agente"), texto)
    if aviso:
        yield {"type": "aviso", "text": aviso}
    yield {"type": "agente", **ag.publico(), "motivo": motivo}
    contexto = db.historial_modelo(cid, MAX_MENSAJES)
    if limpio != texto and contexto and contexto[-1]["role"] == "user":
        contexto[-1] = {"role": "user", "content": limpio}
    acumulado, pendiente, cerebro, toco_memoria = "", None, None, False
    try:
        tope = invitados.herramientas(limites) if limites else None
        async for ev in responder(contexto, usuario["rol"], usuario["nombre"], agente=ag, uid=uid, limite=tope):
            if ev["type"] == "cerebro":
                cerebro = ev["etiqueta"]
            elif ev["type"] == "token":
                acumulado += ev["text"]
            elif ev["type"] == "reinicio":
                acumulado = ""
            elif ev["type"] == "herramienta":
                if acumulado.strip():
                    db.anadir(cid, "assistant", acumulado, cerebro, ag.id)
                acumulado = ""
                pendiente = (ev["name"], ev["args"])
                toco_memoria = toco_memoria or ev["name"] in tools.MEMORIA
            elif ev["type"] == "resultado":
                db.anadir(cid, "tool", db.herramienta_json(ev["name"], pendiente[1] if pendiente else {}, ev["text"]))
            yield ev
    finally:
        # También se ejecuta si el cliente aborta (botón Detener): se conserva lo generado.
        if acumulado.strip():
            db.anadir(cid, "assistant", acumulado, cerebro, ag.id)
        # Aprendizaje automático: en segundo plano y solo con cerebros de la nube. No se aprende de peticiones
        # de recordar/olvidar (ya las atiende la herramienta; «olvida X» no debe volver a aprenderse).
        if (not limites or limites.get("memoria")) and not toco_memoria and not (tools.relevantes(texto) & tools.MEMORIA):
            try:
                aprender.programar(uid, usuario["nombre"], texto)
            except Exception:  # noqa: BLE001
                log.exception("No se pudo programar el aprendizaje")


PREFIJO_IMAGEN = "[imagen]"


async def conversar_imagen(usuario: dict, cid: str | None, texto: str, imagen: bytes, mime: str,
                           proponer: bool = True) -> AsyncIterator[dict]:
    """Como `conversar`, pero con una imagen: la mira un proveedor de visión de la nube (nunca el local).

    La imagen no se guarda: el historial lleva «[imagen] texto» y la respuesta del modelo. Sin herramientas ni
    agentes; si es un ticket se emite un evento «ticket» (con `proponer`, con su ficha para confirmarlo en la web).
    De las imágenes no se aprende nada en segundo plano."""
    texto = (texto or "").strip()[:MAX_CHARS]
    uid = usuario["id"]
    if not cid or not db.existe(cid, uid):
        cid = db.crear(uid)
    if db.es_primer_mensaje(cid):
        db.renombrar(cid, uid, db.titulo_desde(texto) if texto else "Imagen")
    previo = db.historial_modelo(cid, 6)
    db.anadir(cid, "user", f"{PREFIJO_IMAGEN} {texto}".strip())
    conv = db.obtener(cid, uid)
    yield {"type": "conv", "id": cid, "titulo": conv["titulo"], "agente": conv.get("agente") or agentes.AUTO}
    yield {"type": "agente", **agentes.obtener(agentes.AUTO).publico(), "motivo": "imagen"}
    yield {"type": "pensando"}
    try:
        r = await vision.analizar(imagen, mime, texto, usuario, previo)
    except vision.VisionError as e:
        yield {"type": "error", "text": e.mensaje}
        return
    finally:
        imagen = None  # noqa: F841 - la imagen no sobrevive a la petición
    yield {"type": "cerebro", "id": "vision_" + r["proveedor"], "nombre": r["etiqueta"].split(" · ")[0],
           "modelo": r["modelo"], "etiqueta": r["etiqueta"]}
    yield {"type": "token", "text": r["texto"]}
    db.anadir(cid, "assistant", r["texto"], r["etiqueta"], agentes.AUTO)
    if r["ticket"]:
        ev = {"type": "ticket", **vision.publico(r["ticket"])}
        if proponer:
            ev["token"] = vision.proponer(uid, r["ticket"], cid)
        else:
            ev["datos"] = r["ticket"]
        yield ev
    yield {"type": "fin"}
