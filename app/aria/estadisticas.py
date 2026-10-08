"""Estadísticas de consultas DNS por dispositivo e informe semanal.

Pi-hole identifica los clientes por IP. La clave y el nombre visibles se
resuelven contra el inventario local de `red_inventario`.
"""
import asyncio
import time
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta

from . import db, red, shield, tiempo, vpn

_CACHE: dict[tuple, tuple[float, dict]] = {}
_CACHE_S = 60
_BLOQUEADOS = {"GRAVITY", "DENYLIST", "REGEX", "EXTERNAL_BLOCKED", "SPECIAL_DOMAIN", "BLOCKED"}


class EstadisticasError(Exception):
    """Error legible al consultar SHIELD-DNS."""


def _ventana(horas) -> int:
    try:
        h = int(horas)
    except (TypeError, ValueError):
        h = 24
    if h not in (24, 168):
        raise EstadisticasError("La ventana debe ser de 24 o 168 horas.")
    return h


def _nombre(ip: str, filas: list) -> tuple[str, str]:
    for r in filas:
        if r["ip"] == ip:
            return r["alias"] or r["nombre"] or r["fabricante"] or ip, r["clave"]
    return ip, f"ip-{ip}"


def _inventario() -> list:
    try:
        with closing(db._con()) as con:
            return con.execute("SELECT clave, ip, nombre, alias, fabricante FROM red_inventario").fetchall()
    except Exception:  # la tabla se crea durante el arranque
        return []


def _datos_serie(history: dict, horas: int, filas: list) -> dict:
    paso = 3600 if horas == 24 else 86400
    ahora = time.time()
    comienzo = ahora - horas * 3600
    por_clave: dict[str, list] = {}
    for punto in history.get("history") or []:
        ts = float(punto.get("timestamp") or 0)
        if ts < comienzo:
            continue
        # Pi-hole devuelve cubos horarios; para la vista semanal se agrupan por día.
        cubo = int(ts // paso) * paso
        for ip, cantidad in (punto.get("data") or {}).items():
            nombre, clave = _nombre(ip, filas)
            serie = por_clave.setdefault(clave, {"nombre": nombre, "ip": ip, "puntos": {}})
            serie["puntos"][cubo] = serie["puntos"].get(cubo, 0) + int(cantidad or 0)
    return {k: {**v, "serie": [{"ts": ts, "consultas": n} for ts, n in sorted(v["puntos"].items())]}
            for k, v in por_clave.items()}


async def _obtener(horas: int, fin: int | None = None) -> dict:
    ahora = int(time.time()) if fin is None else int(fin)
    desde = ahora - horas * 3600
    if horas == 24:
        rutas = ("/api/history/clients", "/api/stats/top_clients")
        bloqueos = "/api/stats/top_clients"
    else:
        rutas = ("/api/history/database/clients", "/api/stats/database/top_clients")
        bloqueos = "/api/stats/database/top_clients"
    history = await shield._llamar("GET", rutas[0], params={"from": desde, "until": ahora} if horas == 168 else {})
    top, blocked = await asyncio.gather(
        shield._llamar("GET", rutas[1], params={"from": desde, "until": ahora, "count": 500} if horas == 168 else {"count": 500}),
        shield._llamar("GET", bloqueos, params={"from": desde, "until": ahora, "count": 500, "blocked": "true"}
                        if horas == 168 else {"count": 500, "blocked": "true"}),
    )
    inv = _inventario()
    series = _datos_serie(history, horas, inv)
    bloqueadas = {x.get("ip"): int(x.get("count") or 0) for x in blocked.get("clients") or []}
    filas = []
    for x in top.get("clients") or []:
        ip = x.get("ip") or ""
        nombre, clave = _nombre(ip, inv)
        consultas = int(x.get("count") or 0)
        b = bloqueadas.get(ip, 0)
        s = series.get(clave, {"serie": []})["serie"]
        filas.append({"clave": clave, "nombre": nombre, "ip": ip, "consultas": consultas, "bloqueadas": b,
                      "porcentaje": round(b * 100 / consultas, 1) if consultas else 0, "serie": s})
    filas.sort(key=lambda x: x["consultas"], reverse=True)
    total = int(top.get("total_queries") or sum(x["consultas"] for x in filas))
    bloqueadas_total = int(top.get("blocked_queries") or sum(x["bloqueadas"] for x in filas))
    return {"horas": horas, "dispositivos": filas, "totales": {
        "consultas": total, "bloqueadas": bloqueadas_total,
        "porcentaje": round(bloqueadas_total * 100 / total, 1) if total else 0}}


async def resumen(horas=24) -> dict:
    horas = _ventana(horas)
    clave = ("resumen", horas)
    ahora = time.monotonic()
    if clave in _CACHE and ahora - _CACHE[clave][0] < _CACHE_S:
        return _CACHE[clave][1]
    try:
        resultado = await _obtener(horas)
    except shield.ShieldError as e:
        raise EstadisticasError(str(e)) from e
    _CACHE[clave] = (ahora, resultado)
    return resultado


async def detalle(clave: str, horas=24) -> dict:
    horas = _ventana(horas)
    inv = _inventario()
    ip = next((r["ip"] for r in inv if r["clave"] == clave), None)
    if not ip and clave.startswith("ip-"):
        ip = clave[3:]
    if not ip:
        raise EstadisticasError("Dispositivo no encontrado en el inventario.")
    cache_key = ("detalle", clave, horas)
    if cache_key in _CACHE and time.monotonic() - _CACHE[cache_key][0] < _CACHE_S:
        return _CACHE[cache_key][1]
    base = await resumen(horas)
    fila = next((x for x in base["dispositivos"] if x["clave"] == clave or x["ip"] == ip), None)
    ahora = int(time.time())
    params = {"client_ip": ip, "from": ahora - horas * 3600, "until": ahora, "length": 1000}
    permitidos, bloqueados, cursor = Counter(), Counter(), None
    for _ in range(5):
        p = dict(params)
        if cursor:
            p["cursor"] = cursor
        try:
            datos = await shield._llamar("GET", "/api/queries", params=p)
        except shield.ShieldError as e:
            raise EstadisticasError(str(e)) from e
        consultas = datos.get("queries") or []
        if not consultas:
            break
        for q in consultas:
            dominio = q.get("domain") or ""
            if not dominio:
                continue
            status = str(q.get("status") or "").upper()
            (bloqueados if status.startswith(tuple(_BLOQUEADOS)) else permitidos)[dominio] += 1
        nuevo = datos.get("cursor")
        if not nuevo or nuevo == cursor or len(consultas) < 1000:
            break
        cursor = nuevo
    out = {"clave": clave, "nombre": (fila or {}).get("nombre", ip), "ip": ip,
           "serie": (fila or {}).get("serie", []),
           "permitidos": [{"dominio": d, "veces": n} for d, n in permitidos.most_common(10)],
           "bloqueados": [{"dominio": d, "veces": n} for d, n in bloqueados.most_common(10)]}
    _CACHE[cache_key] = (time.monotonic(), out)
    return out


async def construir_informe_semanal(ahora: float | None = None) -> str:
    ahora = time.time() if ahora is None else ahora
    lineas = ["📊 **Informe semanal de ARIA**"]
    try:
        actual = await resumen(168)
        anterior = await _obtener(168, int(ahora) - 7 * 86400)
        t = actual["totales"]
        lineas += ["", "**Bloqueador**", f"• {t['consultas']} consultas, {t['bloqueadas']} bloqueadas ({t['porcentaje']} %)."]
        if anterior["totales"]["consultas"]:
            p = anterior["totales"]["consultas"]
            lineas.append(f"• Semana anterior: {p} consultas ({round((t['consultas'] - p) * 100 / p, 1)} % de cambio).")
        lineas.append("• Más consultas: " + ", ".join(f"{x['nombre']} ({x['consultas']})" for x in actual["dispositivos"][:5]) + ".")
        top = await shield._llamar("GET", "/api/stats/database/top_domains",
                                   params={"from": int(ahora) - 7 * 86400, "until": int(ahora), "blocked": "true", "count": 5})
        if top.get("domains"):
            lineas.append("• Dominios más bloqueados: " + ", ".join(f"{x.get('domain')} ({x.get('count', 0)})" for x in top["domains"]) + ".")
    except EstadisticasError:
        pass
    try:
        clientes = await vpn.listar()
        conectados = [c for c in clientes if c.get("ultimo_handshake") and ahora - _ts(c["ultimo_handshake"]) <= 7 * 86400]
        if conectados:
            lineas += ["", "**VPN (HEIMDALL)**", "• " + ", ".join(f"{c['nombre']} ({_bytes(c['recibido'] + c['enviado'])})" for c in conectados) + "."]
    except Exception:
        pass
    try:
        semana = ahora - 7 * 86400
        with closing(db._con()) as con:
            nuevos = con.execute("SELECT nombre, ip FROM red_inventario WHERE primera_vez>=?", (semana,)).fetchall()
            desconocidos = con.execute("SELECT nombre, ip FROM red_inventario WHERE conocido=0").fetchall()
        if nuevos or desconocidos:
            lineas += ["", "**Red**"]
            if nuevos:
                lineas.append("• Nuevos esta semana: " + ", ".join(r["nombre"] or r["ip"] for r in nuevos[:10]) + ".")
            if desconocidos:
                lineas.append("• Sin nombre: " + ", ".join(r["nombre"] or r["ip"] for r in desconocidos[:10]) + ".")
    except Exception:
        pass
    try:
        from . import avisos, briefing
        copia = briefing.ultima_copia()
        graves = db._con()
        try:
            filas = graves.execute("SELECT texto FROM avisos WHERE severidad='grave' AND creado>=? ORDER BY creado DESC LIMIT 5",
                                   (ahora - 7 * 86400,)).fetchall()
        finally:
            graves.close()
        if copia.get("disponible") or filas:
            lineas += ["", "**Sistema**"]
            if copia.get("disponible"):
                lineas.append("• Última copia: " + str(copia.get("hace", "disponible")) + ".")
            else:
                lineas.append("• Última copia: no disponible.")
            if filas:
                lineas.append("• Avisos graves: " + " | ".join(x["texto"] for x in filas) + ".")
    except Exception:
        pass
    return "\n".join(lineas)


def _ts(v: str) -> float:
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0


def _bytes(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"
