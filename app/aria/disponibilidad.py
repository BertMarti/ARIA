"""Histórico de disponibilidad de los servicios de ARIA."""
import asyncio
import time
from contextlib import closing

import httpx

from . import db

SERVICIOS = ("ARIA", "SHIELD-DNS", "HEIMDALL", "túnel", "Ollama local", "cerebros de la nube",
             "búsqueda", "voz", "escáner", "copias", "internet")
_ultimo_minuto = None


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS disponibilidad (
                servicio TEXT NOT NULL, ts INTEGER NOT NULL, ok INTEGER NOT NULL,
                ms INTEGER NULL, detalle TEXT NOT NULL DEFAULT '' CHECK (length(detalle) <= 120),
                PRIMARY KEY (servicio, ts));
            CREATE INDEX IF NOT EXISTS idx_disponibilidad ON disponibilidad(servicio, ts);
            CREATE TABLE IF NOT EXISTS disponibilidad_hora (
                servicio TEXT NOT NULL, ts INTEGER NOT NULL, muestras INTEGER NOT NULL,
                buenas INTEGER NOT NULL, ms REAL NULL, detalle TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (servicio, ts));
            CREATE INDEX IF NOT EXISTS idx_disponibilidad_hora ON disponibilidad_hora(servicio, ts);
        """)


def registrar(servicio: str, ts: int, ok: bool, ms=None, detalle="") -> None:
    if servicio not in SERVICIOS:
        raise ValueError("Servicio no válido")
    detalle = " ".join(str(detalle or "").split())[:120]
    with closing(db._con()) as con, con:
        con.execute("INSERT OR REPLACE INTO disponibilidad VALUES (?,?,?,?,?)",
                    (servicio, int(ts // 60 * 60), int(bool(ok)), int(ms) if ms is not None else None, detalle))


def _fila(servicio, ok, ms=None, detalle=""):
    return servicio, bool(ok), ms, detalle


async def _muestras() -> list:
    from . import briefing, busqueda, cerebros, escaneo, services, telemetria, voz
    inicio = time.perf_counter()
    try:
        estado = await services.estado()
    except Exception:
        estado = {}
    out = [_fila("ARIA", True, round((time.perf_counter() - inicio) * 1000))]
    s = estado.get("shield_dns") or {}
    h = estado.get("heimdall") or {}
    out += [_fila("SHIELD-DNS", s.get("dns_ok") and s.get("web_ok"), detalle="DNS o panel sin respuesta"),
            _fila("HEIMDALL", h.get("web_ok"), detalle="Panel sin respuesta")]
    try:
        tunel = telemetria.estado_tunel() or {}
        out.append(_fila("túnel", tunel.get("estado") in ("ok", "activo"), detalle=tunel.get("estado", "sin señal")))
    except Exception:
        out.append(_fila("túnel", False, detalle="Sin señal del vigilante"))
    try:
        estados = cerebros.estado()
        local = any("local" in x.get("id", "").lower() and x.get("activo", True) for x in estados)
        nube = cerebros.hay_nube()
    except Exception:
        local, nube = False, False
    out += [_fila("Ollama local", local, detalle="No disponible" if not local else ""),
            _fila("cerebros de la nube", nube, detalle="Ningún proveedor disponible" if not nube else "")]
    try:   # comprobaciones reales (antes miraba si existía el módulo: siempre salía bien)
        async with httpx.AsyncClient(timeout=3) as c:
            t = time.perf_counter()
            ok_b = (await c.get(f"{busqueda.URL}/healthz")).status_code == 200
        out.append(_fila("búsqueda", ok_b, round((time.perf_counter() - t) * 1000), "" if ok_b else "SearXNG no responde"))
    except Exception:
        out.append(_fila("búsqueda", False, detalle="SearXNG no responde"))
    try:
        ok_v = await voz.voz_local_ok()
        out.append(_fila("voz", ok_v, detalle="" if ok_v else "aria-voz no responde"))
    except Exception:
        out.append(_fila("voz", False, detalle="aria-voz no responde"))
    try:
        esc = await asyncio.to_thread(escaneo.estado)
        out.append(_fila("escáner", bool(esc.get("disponible") and esc.get("escaner_vivo")), detalle="Sin señal"))
    except Exception:
        out.append(_fila("escáner", False, detalle="No disponible"))
    try:
        copia = await asyncio.to_thread(briefing.ultima_copia)
        out.append(_fila("copias", bool(copia.get("disponible") and not copia.get("antigua")), detalle="Copia de hace más de 26 h"))
    except Exception:
        out.append(_fila("copias", False, detalle="No disponible"))
    try:   # conexión TCP rápida a un DNS público (barata cada minuto; no depende de que haya medición reciente)
        t = time.perf_counter()
        _, escritor = await asyncio.wait_for(asyncio.open_connection("1.1.1.1", 53), 3)
        escritor.close()
        out.append(_fila("internet", True, round((time.perf_counter() - t) * 1000)))
    except Exception:
        out.append(_fila("internet", False, detalle="Sin conexión a internet"))
    return out


async def ciclo(ahora=None) -> None:
    global _ultimo_minuto
    ahora = int(time.time() if ahora is None else ahora)
    minuto = ahora // 60 * 60
    if minuto == _ultimo_minuto:
        return
    _ultimo_minuto = minuto
    try:
        for servicio, ok, ms, detalle in await _muestras():
            registrar(servicio, minuto, ok, ms, detalle)
    except Exception:
        _ultimo_minuto = None
        raise


def purgar(ahora=None) -> None:
    ahora = int(time.time() if ahora is None else ahora)
    limite = ahora - 30 * 86400
    anual = ahora - 365 * 86400
    with closing(db._con()) as con, con:
        con.execute("""INSERT OR REPLACE INTO disponibilidad_hora
            SELECT servicio, (ts / 3600) * 3600, count(*), sum(ok), avg(ms),
            max(detalle) FROM disponibilidad WHERE ts < ? GROUP BY servicio, (ts / 3600) * 3600""", (limite,))
        con.execute("DELETE FROM disponibilidad WHERE ts < ?", (limite,))
        con.execute("DELETE FROM disponibilidad_hora WHERE ts < ?", (anual,))


def _filas(desde, hasta):
    with closing(db._con()) as con:
        return con.execute("SELECT servicio, ts, ok, ms, detalle FROM disponibilidad WHERE ts>=? AND ts<? "
                           "ORDER BY servicio, ts", (desde, hasta)).fetchall()


def _incidentes(filas, hasta):
    out, actual = [], None
    for r in filas + [None]:
        malo = r is not None and not r["ok"]
        clave = r["servicio"] if malo else None
        if actual and clave != actual["servicio"]:
            actual["fin"] = actual["ultimo"] + 60
            actual["duracion"] = max(60, actual["fin"] - actual["inicio"])
            out.append(actual)
            actual = None
        if malo and not actual:
            actual = {"servicio": clave, "inicio": r["ts"], "ultimo": r["ts"], "detalle": r["detalle"]}
        elif malo and r["ts"] <= actual["ultimo"] + 60:
            actual["ultimo"] = r["ts"]
            actual["detalle"] = actual["detalle"] or r["detalle"]
        elif actual:
            actual["fin"] = actual["ultimo"] + 60
            actual["duracion"] = max(60, actual["fin"] - actual["inicio"])
            out.append(actual)
            actual = {"servicio": clave, "inicio": r["ts"], "ultimo": r["ts"], "detalle": r["detalle"]} if malo else None
    for x in out:
        x.pop("ultimo", None)
    return out


def resumen(dias=1, ahora=None) -> dict:
    ahora = int(time.time() if ahora is None else ahora)
    desde = ahora - dias * 86400
    filas = _filas(desde, ahora + 60)
    resultado = []
    for servicio in SERVICIOS:
        fs = [r for r in filas if r["servicio"] == servicio]
        buenas = sum(r["ok"] for r in fs)
        p = round(buenas * 100 / len(fs), 1) if fs else None
        ms = [r["ms"] for r in fs if r["ms"] is not None]
        caidas = _incidentes(fs, ahora)
        serie = []
        paso = 3600 if dias == 1 else 86400
        for ts in range(desde // paso * paso, ahora + paso, paso):
            cubo = [r for r in fs if ts <= r["ts"] < ts + paso]
            serie.append({"ts": ts, "ok": round(sum(r["ok"] for r in cubo) * 100 / len(cubo), 1) if cubo else None,
                          "peor": "rojo" if any(not r["ok"] for r in cubo) else "verde" if cubo else "gris"})
        resultado.append({"servicio": servicio, "porcentaje": p, "caidas": len(caidas),
                          "mas_larga": max((x["duracion"] for x in caidas), default=0),
                          "latencia_media": round(sum(ms) / len(ms), 1) if ms else None, "serie": serie})
    return {"dias": dias, "servicios": resultado}


def incidentes(dias=30, ahora=None) -> list:
    ahora = int(time.time() if ahora is None else ahora)
    return _incidentes(_filas(ahora - dias * 86400, ahora + 60), ahora)


def texto_24h() -> str:
    d = resumen(1)
    vals = [x["porcentaje"] for x in d["servicios"] if x["porcentaje"] is not None]
    inc = incidentes(1)
    if not vals:
        return "Disponibilidad 24 h: sin datos"
    extra = f" · {len(inc)} caída" + ("s" if len(inc) != 1 else "")
    if inc:
        x = inc[0]
        extra += f" ({x['servicio']}, {max(1, x['duracion'] // 60)} min)"
    return f"Disponibilidad 24 h: {sum(vals) / len(vals):.1f} %".replace(".", ",") + extra
