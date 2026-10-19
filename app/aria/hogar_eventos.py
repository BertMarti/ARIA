"""Eventos: detecciones (movimiento, personas…) de las cámaras de la vigilancia mientras no hay nadie en casa.

Solo se consulta a las cámaras elegidas en la vigilancia y solo con el estado en «fuera» (las de batería no se
despiertan a cada rato). Cada evento se guarda una vez (cámara + inicio) con una foto pequeña del momento, y se
avisa como mucho una vez cada cinco minutos por cámara. El vídeo se ve con el clip de la grabación: cada detección
coincide con un fragmento de la tarjeta SD (grabación por eventos).
"""
import asyncio
import datetime as dt
import logging
import time
from contextlib import closing
from zoneinfo import ZoneInfo

from . import avisos, config, db, hogar_cache, hogar_camaras, hogar_grabaciones, hogar_vigilancia

log = logging.getLogger("aria.eventos")
INTERVALO_S = 60
VENTANA_S = 3600          # la cámara falla con rangos de más de ~1 día; con una hora sobra
SOLAPE_S = 60             # se repite el último minuto por si la cámara apuntó algo tarde (se deduplica)
AVISO_CADA_S = 300
MAX_FILAS = 300
MAX_DIAS = 30
MAX_FOTO = 200 * 1024
_consultado: dict = {}    # ip -> último instante consultado
_avisado: dict = {}       # ip -> momento del último aviso


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS hogar_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT NOT NULL, inicio INTEGER NOT NULL, fin INTEGER NOT NULL,
            tipo INTEGER NOT NULL DEFAULT 0, foto BLOB, visto INTEGER NOT NULL DEFAULT 0, creado REAL NOT NULL,
            UNIQUE(ip, inicio))""")


def _zona() -> ZoneInfo:
    try:
        return ZoneInfo(config.TZ)
    except Exception:  # noqa: BLE001
        return ZoneInfo("Europe/Madrid")


def dia_local(ts: int) -> str:
    """Día (AAAA-MM-DD) en la hora de casa: el que usa la cámara para sus grabaciones."""
    return dt.datetime.fromtimestamp(ts, _zona()).strftime("%Y-%m-%d")


def hora_local(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, _zona()).strftime("%H:%M")


def nombre_camara(ip: str) -> str:
    for c in hogar_cache.ultimo("camaras") or []:
        if isinstance(c, dict) and c.get("ip") == ip and c.get("nombre") and c["nombre"] != ip:
            return str(c["nombre"])
    return "una cámara"


def _purgar(con, ahora: float) -> None:
    con.execute("DELETE FROM hogar_eventos WHERE inicio < ?", (int(ahora) - MAX_DIAS * 86400,))
    con.execute("DELETE FROM hogar_eventos WHERE id NOT IN (SELECT id FROM hogar_eventos ORDER BY inicio DESC, id DESC LIMIT ?)",
                (MAX_FILAS,))


def _insertar(ip: str, eventos: list, ahora: float) -> list:
    """Guarda los que no estaban (cámara + inicio). Devuelve [(id, inicio)] de los nuevos, el más reciente primero."""
    nuevos = []
    with closing(db._con()) as con, con:
        for e in eventos:
            try:
                inicio, fin, tipo = int(e["inicio"]), int(e["fin"]), int(e.get("tipo", 0))
            except (KeyError, TypeError, ValueError):
                continue
            if inicio <= 0 or fin < inicio:
                continue
            cur = con.execute("INSERT OR IGNORE INTO hogar_eventos(ip, inicio, fin, tipo, creado) VALUES(?,?,?,?,?)",
                              (ip, inicio, fin, tipo, ahora))
            if cur.rowcount == 1:
                nuevos.append((cur.lastrowid, inicio))
            else:   # ya estaba: si la cámara alargó la detección, se apunta el nuevo fin
                con.execute("UPDATE hogar_eventos SET fin=? WHERE ip=? AND inicio=? AND fin<?", (fin, ip, inicio, fin))
        _purgar(con, ahora)
    return sorted(nuevos, key=lambda x: x[1], reverse=True)


def _guardar_foto(evento_id: int, datos: bytes) -> None:
    with closing(db._con()) as con, con:
        con.execute("UPDATE hogar_eventos SET foto=? WHERE id=?", (datos, evento_id))


async def _consultar(ip: str, desde: int, hasta: int) -> list:
    r = await hogar_grabaciones.consultar("/eventos", {"cam": hogar_camaras.flujo(ip), "desde": desde, "hasta": hasta})
    if r.status_code != 200:
        raise RuntimeError("El servicio de grabaciones no ha respondido.")
    eventos = r.json().get("eventos")
    return eventos if isinstance(eventos, list) else []


async def ciclo(ahora: float | None = None) -> int:
    """Una vuelta: consulta las cámaras de la vigilancia si no hay nadie en casa. Devuelve cuántos eventos nuevos."""
    ahora = int(time.time() if ahora is None else ahora)
    if not hogar_camaras.disponible():
        return 0
    f = await asyncio.to_thread(hogar_vigilancia._fila)
    if not f["ajustes"]["activa"] or f["estado"] != "fuera":
        return 0
    total = 0
    for ip in f["ajustes"]["camaras"]:
        if not hogar_camaras.flujo(ip):
            continue
        desde = max(_consultado.get(ip, 0) - SOLAPE_S, ahora - VENTANA_S)
        if desde >= ahora:
            continue
        try:
            eventos = await _consultar(ip, desde, ahora)
        except Exception:  # noqa: BLE001 - la cámara puede estar dormida o el servicio arrancando
            log.info("Eventos: no se pudo consultar una cámara")
            continue
        _consultado[ip] = ahora
        nuevos = await asyncio.to_thread(_insertar, ip, eventos, ahora)
        if not nuevos:
            continue
        total += len(nuevos)
        try:   # una foto del momento para el más reciente (si la cámara no la da, el evento se guarda igual)
            datos = await hogar_camaras.foto(ip, 0)
            if datos and len(datos) <= MAX_FOTO:
                await asyncio.to_thread(_guardar_foto, nuevos[0][0], datos)
        except Exception:  # noqa: BLE001
            log.info("Eventos: la cámara no ha dado imagen")
        if ahora - _avisado.get(ip, 0) >= AVISO_CADA_S:
            _avisado[ip] = ahora
            await avisos.emitir("vigilancia", "grave",
                                f"Movimiento en {nombre_camara(ip)} a las {hora_local(nuevos[0][1])} y no hay nadie en casa.",
                                "hogar")
    return total


async def bucle() -> None:
    await asyncio.sleep(90)
    while True:
        try:
            await ciclo()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Fallo al consultar los eventos de las cámaras")
        await asyncio.sleep(INTERVALO_S)


def listar(limite: int = 50) -> list:
    """Los últimos eventos, sin la foto (solo si la tiene), con el nombre de la cámara y su día local."""
    limite = max(1, min(int(limite), MAX_FILAS))
    with closing(db._con()) as con:
        filas = con.execute("SELECT id, ip, inicio, fin, tipo, visto, foto IS NOT NULL AS tiene_foto FROM hogar_eventos "
                            "ORDER BY inicio DESC, id DESC LIMIT ?", (limite,)).fetchall()
    return [{"id": f["id"], "ip": f["ip"], "nombre": nombre_camara(f["ip"]), "inicio": f["inicio"], "fin": f["fin"],
             "tipo": f["tipo"], "tiene_foto": bool(f["tiene_foto"]), "visto": bool(f["visto"]), "dia": dia_local(f["inicio"])}
            for f in filas]


def foto(evento_id: int) -> bytes | None:
    with closing(db._con()) as con:
        f = con.execute("SELECT foto FROM hogar_eventos WHERE id=?", (evento_id,)).fetchone()
    return bytes(f["foto"]) if f and f["foto"] else None


def marcar_vistos() -> int:
    with closing(db._con()) as con, con:
        return con.execute("UPDATE hogar_eventos SET visto=1 WHERE visto=0").rowcount
