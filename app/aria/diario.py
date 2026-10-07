"""Diario diario: resumen breve de lo que hizo cada usuario ese día (tabla `diario`).

Un planificador asyncio dentro de la propia app (sin contenedor nuevo) lo genera a las ~03:30 locales
y, al arrancar, recupera los días que se hayan perdido. Resume un cerebro de la nube; si no hay
ninguno, se guarda un resumen extractivo con los títulos de las conversaciones del día."""
import asyncio
import logging
from contextlib import closing
from datetime import date, datetime, time as hora, timedelta

from . import cerebros, db, memoria, tiempo

log = logging.getLogger("aria.diario")

HORA_JOB = hora(3, 30)
DIAS_ATRASO = 14            # cuántos días hacia atrás se recuperan al arrancar
RETRASO_ARRANQUE_S = 45     # deja arrancar al resto antes de recuperar días
MAX_CHARS_ENTRADA = 7000

PROMPT = (
    "Tarea interna: resume en español de España el día de {nombre} a partir de sus conversaciones con ARIA "
    "({fecha}). Escribe de 3 a 5 viñetas MUY breves (cada una empieza por «- »): qué preguntó o hizo, "
    "decisiones tomadas y cosas pendientes de seguimiento. Máximo 500 caracteres en total. No incluyas "
    "contraseñas, claves, tokens ni números de tarjeta o de documentos. Responde solo con las viñetas.\n\n"
    "CONVERSACIONES:\n<<<\n{texto}\n>>>"
)


def _mensajes_del_dia(uid: int, dia: date) -> tuple[list, list]:
    """(mensajes user/assistant del día, títulos de las conversaciones con actividad ese día)."""
    ini, fin = tiempo.limites(dia)
    with closing(db._con()) as con:
        msgs = con.execute(
            "SELECT m.rol, m.contenido, c.id AS cid, c.titulo FROM mensajes m JOIN conversaciones c ON c.id=m.conv_id "
            "WHERE c.user_id=? AND m.ts>=? AND m.ts<? AND m.rol IN ('user','assistant') ORDER BY m.id",
            (uid, ini, fin)).fetchall()
    titulos = list(dict.fromkeys(m["titulo"] for m in msgs))
    return [dict(m) for m in msgs], titulos


def usuarios_con_mensajes(dia: date) -> list:
    ini, fin = tiempo.limites(dia)
    with closing(db._con()) as con:
        return [r[0] for r in con.execute(
            "SELECT DISTINCT c.user_id FROM mensajes m JOIN conversaciones c ON c.id=m.conv_id "
            "WHERE c.user_id IS NOT NULL AND m.rol='user' AND m.ts>=? AND m.ts<? ORDER BY c.user_id", (ini, fin))]


def _transcripcion(msgs: list) -> str:
    out, total = [], 0
    for m in msgs:
        t = " ".join(m["contenido"].split())[:300 if m["rol"] == "user" else 160]
        linea = ("Usuario: " if m["rol"] == "user" else "ARIA: ") + t
        if total + len(linea) > MAX_CHARS_ENTRADA:
            break
        out.append(linea)
        total += len(linea) + 1
    return "\n".join(out)


def extractivo(titulos: list) -> str:
    """Resumen sin IA: los títulos de las conversaciones del día."""
    if not titulos:
        return ""
    resumen = "\n".join("- " + t for t in titulos[:6])
    return memoria.limpiar_dia("Conversaciones del día:\n" + resumen)


def _limpiar_vinetas(texto: str) -> str:
    out = []
    for l in (texto or "").splitlines():
        l = l.strip().lstrip("-•*·").strip()
        if l and not memoria.parece_secreto(l):
            out.append("- " + l)
    return memoria.limpiar_dia("\n".join(out[:5]))


async def generar(uid: int, nombre: str, dia: date, forzar: bool = False) -> str:
    """Genera y guarda el resumen de `dia`. Devuelve: 'cerebro' | 'extractivo' | 'existente' | 'sin_mensajes' | 'desactivado'."""
    fecha = dia.isoformat()
    if not forzar and memoria.dia(uid, fecha):
        return "existente"
    if not memoria.aprende(uid):
        return "desactivado"  # quien no quiere que ARIA aprenda de sus conversaciones tampoco tiene diario
    msgs, titulos = await asyncio.to_thread(_mensajes_del_dia, uid, dia)
    if not msgs:
        return "sin_mensajes"
    resumen, via = "", "extractivo"
    if cerebros.hay_nube():
        r = await cerebros.completar_nube(PROMPT.format(nombre=memoria.limpiar(nombre) or "el usuario", fecha=fecha,
                                                        texto=_transcripcion(msgs)))
        if r:
            resumen, via = _limpiar_vinetas(r[0]), "cerebro"
    if not resumen:
        resumen, via = extractivo(titulos), "extractivo"
    if not resumen:
        return "sin_mensajes"
    await asyncio.to_thread(memoria.guardar_dia, uid, fecha, resumen)
    return via


def _usuarios() -> dict:
    from . import usuarios
    return {u["id"]: u["nombre"] for u in usuarios.listar() if u["activo"]}


async def ponerse_al_dia(hasta: date | None = None, dias: int = DIAS_ATRASO) -> dict:
    """Genera los días sin resumen (hasta ayer inclusive) de los últimos `dias`. Devuelve {fecha: {uid: resultado}}."""
    fin = hasta or tiempo.ayer()
    nombres = await asyncio.to_thread(_usuarios)
    hecho: dict = {}
    for i in range(dias - 1, -1, -1):
        d = fin - timedelta(days=i)
        for uid in await asyncio.to_thread(usuarios_con_mensajes, d):
            if uid not in nombres:
                continue
            try:
                r = await generar(uid, nombres[uid], d)
            except Exception:  # noqa: BLE001 - un fallo no debe impedir el resto
                log.exception("No se pudo generar el diario de %s (%s)", uid, d)
                continue
            if r in ("cerebro", "extractivo"):
                hecho.setdefault(d.isoformat(), {})[uid] = r
    return hecho


def proxima_ejecucion(ref: datetime | None = None) -> datetime:
    """Próxima aparición de las 03:30 en hora local (siempre posterior a `ref`)."""
    ahora = ref.astimezone(tiempo.zona()) if ref else tiempo.ahora()
    hoy = datetime.combine(ahora.date(), HORA_JOB, tzinfo=tiempo.zona())
    return hoy if hoy > ahora else datetime.combine(ahora.date() + timedelta(days=1), HORA_JOB, tzinfo=tiempo.zona())


async def bucle() -> None:
    """Tarea de fondo: recupera días perdidos al arrancar y luego se ejecuta cada noche a las 03:30."""
    primera = True
    while True:
        try:
            if primera:
                primera = False
                await asyncio.sleep(RETRASO_ARRANQUE_S)
                hecho = await ponerse_al_dia()
                if hecho:
                    log.info("Diario: recuperados %d día(s) pendientes", len(hecho))
            objetivo = proxima_ejecucion()
            while True:  # se duerme a trozos por si el reloj salta (cambio de hora, NTP)
                falta = (objetivo - tiempo.ahora()).total_seconds()
                if falta <= 0:
                    break
                await asyncio.sleep(min(falta, 1800))
            hecho = await ponerse_al_dia()
            log.info("Diario: job de las 03:30 terminado (%d día(s) generados)", len(hecho))
            await asyncio.sleep(90)  # evita repetir si el reloj se retrasa un instante
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - el planificador no debe morir
            log.exception("Fallo en el planificador del diario; se reintenta en 5 minutos")
            await asyncio.sleep(300)
