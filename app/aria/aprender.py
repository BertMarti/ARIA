"""Aprendizaje automático de recuerdos: tras cada turno, y FUERA de la petición, un cerebro de la nube
extrae como máximo 3 datos personales duraderos del último mensaje del usuario.

Nunca se usa el cerebro local (es lento y compite con el chat): sin nube disponible, no se aprende nada."""
import asyncio
import json
import logging
import re

from . import cerebros, memoria, proyectos

log = logging.getLogger("aria.memoria")

MAX_NUEVOS = 3
MIN_CHARS = 20
ESPERA_INICIAL_S = 3        # deja pasar el final de la respuesta antes de gastar cuota
_semaforo: asyncio.Semaphore | None = None
_tareas: set = set()        # referencias fuertes: las tareas sueltas pueden recogerse antes de acabar

PROMPT = (
    "Tarea interna: extrae del MENSAJE hasta {n} datos personales DURADEROS que {nombre} dice de sí mismo/a, "
    "de su casa o de sus preferencias (gustos, familia, mascotas, aficiones, rutinas, equipo favorito, "
    "alergias, lugar donde vive...). No extraigas preguntas, órdenes puntuales, opiniones sobre temas ajenos "
    "ni datos pasajeros. NUNCA incluyas contraseñas, claves, tokens, números de tarjeta, de cuenta o de "
    "documentos de identidad, ni datos de acceso. Redacta cada dato en español, en tercera persona y breve "
    "(máximo 200 caracteres), por ejemplo «Su equipo de fútbol es el Betis».\n"
    "Responde SOLO con JSON estricto, sin texto extra ni bloques de código: "
    '{{"hechos": ["...", "..."], "decisiones": [{{"proyecto": "nombre exacto", "decision": "...", "motivo": "..."}}]}}. '
    "Incluye una decisión solo si el mensaje dice claramente que se ha decidido algo y el proyecto aparece en la lista. "
    "Si no hay nada: {{\"hechos\": [], \"decisiones\": []}}.\n\n"
    "MENSAJE:\n<<<\n{mensaje}\n>>>"
)


def parsear(respuesta: str) -> list:
    """Lista de textos candidatos a partir de la respuesta del modelo (JSON estricto o con ruido alrededor)."""
    t = (respuesta or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I)
    datos = None
    for intento in (t, t[t.find("{"):t.rfind("}") + 1] if "{" in t else "", t[t.find("["):t.rfind("]") + 1] if "[" in t else ""):
        if not intento:
            continue
        try:
            datos = json.loads(intento)
            break
        except ValueError:
            continue
    if isinstance(datos, dict):
        datos = datos.get("hechos")
    if not isinstance(datos, list):
        return []
    return [memoria.limpiar(x) for x in datos if isinstance(x, str) and memoria.limpiar(x)]


def parsear_decisiones(respuesta: str, existentes: list) -> list:
    """Devuelve decisiones solo si el modelo nombra exactamente un proyecto existente."""
    try:
        t = (respuesta or "").strip()
        datos = json.loads(t[t.find("{"):t.rfind("}") + 1])
        datos = datos.get("decisiones", []) if isinstance(datos, dict) else []
    except (ValueError, TypeError):
        return []
    nombres = {memoria.normalizar(p["nombre"]): p for p in existentes}
    out = []
    for d in datos:
        if not isinstance(d, dict):
            continue
        p = nombres.get(memoria.normalizar(d.get("proyecto", "")))
        texto = memoria.limpiar(d.get("decision", ""))
        if p and texto and len(texto) <= 500 and not memoria.parece_secreto(texto):
            out.append((p["id"], texto, memoria.limpiar(d.get("motivo", ""))[:500]))
    return out


def guardar(uid: int, candidatos: list) -> list:
    """Filtra (secretos, longitud, duplicados) y guarda como 'auto'. Devuelve los textos guardados."""
    guardados = []
    for texto in candidatos:
        if len(guardados) >= MAX_NUEVOS:
            break
        if len(texto) > memoria.MAX_TEXTO:
            texto = texto[:memoria.MAX_TEXTO - 1].rsplit(" ", 1)[0] + "…"
        try:
            rec, nuevo = memoria.anadir(uid, texto, "auto")
        except memoria.MemoriaError:
            continue  # secreto, vacío...
        if nuevo and rec:
            guardados.append(rec["texto"])
    return guardados


def merece_la_pena(texto: str) -> bool:
    """Evita gastar cuota con saludos y mensajes muy cortos."""
    return len(memoria.limpiar(texto)) >= MIN_CHARS and not memoria.parece_secreto(texto)


async def extraer(uid: int, nombre: str, texto: str) -> list:
    """Pregunta a un cerebro de la nube y guarda lo aprendido. Devuelve los textos nuevos ([] si nada)."""
    if not merece_la_pena(texto) or not memoria.aprende(uid):
        return []
    if not cerebros.hay_nube():
        return []
    r = await cerebros.completar_nube(PROMPT.format(n=MAX_NUEVOS, nombre=memoria.limpiar(nombre) or "el usuario",
                                                     mensaje=memoria.limpiar(texto)[:1500]))
    if not r:
        return []
    guardados = guardar(uid, parsear(r[0]))
    for pid, decision, motivo in parsear_decisiones(r[0], proyectos.listar(uid)):
        try:
            proyectos.registrar_decision(uid, pid, decision, motivo)
        except proyectos.ProyectoError:
            pass
    return guardados


async def _tarea(uid: int, nombre: str, texto: str) -> None:
    global _semaforo
    if _semaforo is None:
        _semaforo = asyncio.Semaphore(1)  # una extracción a la vez: prioridad baja frente al chat
    try:
        await asyncio.sleep(ESPERA_INICIAL_S)
        async with _semaforo:
            nuevos = await extraer(uid, nombre, texto)
        if nuevos:
            log.info("Memoria: %d recuerdo(s) automático(s) nuevo(s) para el usuario %s", len(nuevos), uid)
    except Exception:  # noqa: BLE001 - es un extra: jamás debe afectar al chat
        log.exception("Fallo al extraer recuerdos")


def programar(uid: int, nombre: str, texto: str) -> asyncio.Task | None:
    """Lanza la extracción en segundo plano (no espera). Llamar desde dentro del bucle de eventos."""
    if not merece_la_pena(texto) or not memoria.aprende(uid):
        return None
    t = asyncio.get_running_loop().create_task(_tarea(uid, nombre, texto))
    _tareas.add(t)
    t.add_done_callback(_tareas.discard)
    return t
