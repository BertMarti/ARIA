"""Búsqueda global de los datos personales del usuario autenticado."""
from contextlib import closing
from datetime import datetime, timedelta
from urllib.parse import quote

from . import agenda, db, memoria, notas, recordatorios, tiempo

MAX_POR_TIPO = 8
MAX_TOTAL = 30


def _fragmento(texto: str, q: str) -> str:
    texto = " ".join(str(texto or "").split())
    nq = memoria.normalizar(q)
    nt = memoria.normalizar(texto)
    posicion = nt.find(nq) if nq else -1
    if posicion < 0:
        posicion = 0
    # La normalización puede cambiar la longitud; aproximamos la posición original.
    original = texto[max(0, posicion - 45):posicion + 75]
    prefijo = "…" if posicion else ""
    sufijo = "…" if posicion + 75 < len(texto) else ""
    return (prefijo + original.rstrip() + sufijo)[:120]


def _resultado(tipo, identificador, titulo, detalle, fecha, enlace):
    return {"tipo": tipo, "id": identificador, "titulo": titulo, "detalle": detalle[:120],
            "fecha": fecha, "enlace": enlace}


def _orden(resultado):
    fecha = resultado["fecha"]
    if isinstance(fecha, (int, float)):
        return float(fecha)
    try:
        return datetime.fromisoformat(str(fecha).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0


def _permitidos(limites):
    if not limites:
        return {"notas", "agenda", "cumpleanos", "recordatorios", "conversaciones", "recuerdos"}
    secciones = set(limites.get("secciones", []))
    return {"recordatorios"} | ({"conversaciones"} if "chat" in secciones else set()) \
        | ({"agenda", "cumpleanos"} if "agenda" in secciones else set()) \
        | ({"notas", "recuerdos"} if limites.get("memoria") else set())


def buscar(uid: int, consulta, limites: dict | None = None) -> list:
    """Devuelve coincidencias del usuario; `limites` solo recorta perfiles invitados."""
    q = str(consulta or "").strip()
    if len(q) < 2 or len(q) > 100:
        return []
    nq = memoria.normalizar(q)
    permitidos = _permitidos(limites)
    grupos = {k: [] for k in permitidos}
    ahora = tiempo.ahora()

    def coincide(*valores):
        return any(nq in memoria.normalizar(v) for v in valores if v is not None)

    if "notas" in permitidos:
        for n in notas.listar(uid):
            if coincide(n["texto"]):
                grupos["notas"].append(_resultado("nota", n["id"], n["texto"], _fragmento(n["texto"], q), n["actualizado"], "#notas"))

    if "agenda" in permitidos:
        desde = (ahora - timedelta(days=30)).isoformat(timespec="minutes")
        hasta = (ahora + timedelta(days=330)).isoformat(timespec="minutes")
        for e in agenda.listar_eventos(uid, desde, hasta):
            if coincide(e["titulo"], e.get("lugar")):
                grupos["agenda"].append(_resultado("evento", e["id"], e["titulo"],
                    _fragmento(e["titulo"] + (" · " + e["lugar"] if e.get("lugar") else ""), q), e["inicio"], "#agenda"))

    if "cumpleanos" in permitidos:
        for c in agenda.listar_cumpleanos(uid, 365, ahora):
            if coincide(c["nombre"]):
                grupos["cumpleanos"].append(_resultado("cumpleanos", c["id"], "Cumpleaños de " + c["nombre"],
                    _fragmento(c["nombre"], q), c["fecha"], "#agenda"))

    if "recordatorios" in permitidos:
        for r in recordatorios.listar(uid, ahora):
            if coincide(r["texto"]):
                grupos["recordatorios"].append(_resultado("recordatorio", r["id"], r["texto"], _fragmento(r["texto"], q), r["cuando"],
                    "#ajustes"))

    if "recuerdos" in permitidos:
        for r in memoria.listar(uid):
            if coincide(r["texto"]):
                grupos["recuerdos"].append(_resultado("recuerdo", r["id"], r["texto"], _fragmento(r["texto"], q), r["creado"], "#ajustes"))

    if "conversaciones" in permitidos:
        with closing(db._con()) as con:
            filas = con.execute("SELECT id, titulo, actualizada FROM conversaciones WHERE user_id=? "
                                "ORDER BY actualizada DESC LIMIT 200", (uid,)).fetchall()
            for c in filas:
                mensajes = con.execute("SELECT contenido FROM mensajes WHERE conv_id=? AND rol='user' "
                                       "ORDER BY id DESC", (c["id"],)).fetchall()
                msg = next((m for m in mensajes if coincide(m["contenido"])), None)
                if coincide(c["titulo"]) or msg:
                    detalle = c["titulo"] if coincide(c["titulo"]) else msg["contenido"]
                    grupos["conversaciones"].append(_resultado("conversacion", c["id"], c["titulo"], _fragmento(detalle, q),
                        c["actualizada"], "#chat?c=" + quote(c["id"], safe="")))

    resultados = []
    for grupo in grupos.values():
        resultados.extend(sorted(grupo, key=lambda x: (_orden(x), str(x["id"])), reverse=True)[:MAX_POR_TIPO])
    return sorted(resultados, key=lambda x: (_orden(x), str(x["id"])), reverse=True)[:MAX_TOTAL]
