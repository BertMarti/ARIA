"""Vigilancia automática: si los móviles de la familia llevan un rato fuera de la wifi, se destapa la cámara elegida;
en cuanto vuelve uno, se tapa otra vez. Los móviles se reconocen por su MAC en el router (Android usa una MAC
aleatoria pero fija para cada red wifi).

Prudencia: si el router no responde, no se cambia nada; solo se actúa al cambiar de «casa» a «fuera» o al revés (si
alguien toca la privacidad a mano, se respeta hasta el siguiente cambio).
"""
import asyncio
import hashlib
import json
import logging
import time
from contextlib import closing

from . import avisos, db, hogar_router, hogar_tapo

log = logging.getLogger("aria.vigilancia")
INTERVALO_S = 120
MINUTOS_DEFECTO = 10


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS hogar_vigilancia (
            id INTEGER PRIMARY KEY CHECK(id=1), ajustes TEXT NOT NULL, estado TEXT NOT NULL DEFAULT 'casa',
            desde REAL, vistos TEXT NOT NULL DEFAULT '{}')""")
        con.execute("INSERT OR IGNORE INTO hogar_vigilancia(id, ajustes, desde) VALUES(1, ?, ?)",
                    (json.dumps({"activa": False, "minutos": MINUTOS_DEFECTO, "camaras": [], "moviles": []}), time.time()))


def _fila() -> dict:
    iniciar()
    with closing(db._con()) as con:
        f = con.execute("SELECT * FROM hogar_vigilancia WHERE id=1").fetchone()
    return {"ajustes": json.loads(f["ajustes"]), "estado": f["estado"], "desde": f["desde"], "vistos": json.loads(f["vistos"])}


def _guardar(**campos) -> None:
    with closing(db._con()) as con, con:
        for k, v in campos.items():
            con.execute(f"UPDATE hogar_vigilancia SET {k}=? WHERE id=1",
                        (json.dumps(v) if k in ("ajustes", "vistos") else v,))


def ident(mac: str) -> str:
    """Identificador para el navegador: la MAC entera no sale de ARIA."""
    return hashlib.sha256(hogar_router.mac_completa(mac).encode()).hexdigest()[:12]


def ajustes() -> dict:
    return _fila()["ajustes"]


def configurar(datos: dict, candidatos: list) -> dict:
    """datos: {activa, minutos, camaras: [ip], moviles: [id]}. Los ids se traducen a MAC con la lista del router."""
    actual = ajustes()
    if "activa" in datos:
        if not isinstance(datos["activa"], bool):
            raise ValueError("«activa» no es válido.")
        actual["activa"] = datos["activa"]
    if "minutos" in datos:
        m = datos["minutos"]
        if isinstance(m, bool) or not isinstance(m, int) or not 5 <= m <= 120:
            raise ValueError("Los minutos deben estar entre 5 y 120.")
        actual["minutos"] = m
    if "camaras" in datos:
        if not isinstance(datos["camaras"], list) or not all(isinstance(x, str) for x in datos["camaras"]):
            raise ValueError("Cámaras no válidas.")
        actual["camaras"] = datos["camaras"][:10]
    if "moviles" in datos:
        if not isinstance(datos["moviles"], list):
            raise ValueError("Móviles no válidos.")
        por_id = {ident(c["mac"]): c for c in candidatos}
        previos = {ident(m["mac"]): m for m in actual["moviles"]}   # los que hoy no están conectados se conservan
        nuevos = []
        for i in datos["moviles"][:10]:
            c = por_id.get(i) or previos.get(i)
            if c is None:
                raise ValueError("Ese móvil no está en la lista del router.")
            nuevos.append({"mac": hogar_router.mac_completa(c["mac"]), "nombre": c["nombre"].strip()[:60],
                           "ip": c.get("ip", "")})
        actual["moviles"] = nuevos
    if actual["activa"] and (not actual["moviles"] or not actual["camaras"]):
        raise ValueError("Elige al menos un móvil y una cámara antes de activarla.")
    estaba = ajustes()["activa"]
    _guardar(ajustes=actual)
    if actual["activa"] and not estaba:   # se empieza en «casa» y se cuenta el tiempo desde ahora
        _guardar(estado="casa", desde=time.time())
    return actual


def resumen(candidatos: list | None = None) -> dict:
    f = _fila()
    a = f["ajustes"]
    presentes = {hogar_router.mac_completa(c["mac"]) for c in (candidatos or [])}
    moviles = [{"id": ident(m["mac"]), "nombre": m["nombre"],
                "ultima_vez": f["vistos"].get(m["mac"]), "en_casa": m["mac"] in presentes if candidatos is not None else None}
               for m in a["moviles"]]
    elegidos = {m["id"] for m in moviles}
    return {"activa": a["activa"], "minutos": a["minutos"], "camaras": a["camaras"], "moviles": moviles,
            "estado": f["estado"], "desde": f["desde"],
            "candidatos": [{"id": ident(c["mac"]), "nombre": c["nombre"], "ip": c["ip"]}
                           for c in (candidatos or []) if ident(c["mac"]) not in elegidos]}


async def _poner_privacidad(camaras: list, activa: bool) -> list:
    fallidas = []
    for ip in camaras:
        try:
            await hogar_tapo.privacidad(ip, activa)
        except Exception:  # noqa: BLE001 - una cámara caída no impide las demás
            log.warning("Vigilancia: no se pudo cambiar la privacidad de una cámara")
            fallidas.append(ip)
    return fallidas


def _responde(ip: str) -> bool:
    """¿Contesta al ping? (segunda señal: con la malla, un móvil que cambia de nodo puede faltar un momento en la lista)."""
    from . import red
    if not ip:
        return False
    try:
        return any(red._ping_icmp(ip, n, timeout=1.5) is not None for n in (1, 2))
    except OSError:
        return False


async def ciclo(ahora: float | None = None) -> str | None:
    """Una vuelta. Devuelve el cambio hecho («fuera», «casa») o None.

    Un móvil está en casa si sale en la lista del router o si contesta al ping en su última IP. Para destapar la cámara
    hace falta que el router responda (si no se sabe, no se destapa); para taparla basta con cualquiera de las dos."""
    ahora = time.time() if ahora is None else ahora
    f = await asyncio.to_thread(_fila)
    a = f["ajustes"]
    if not a["activa"] or not a["moviles"] or not a["camaras"]:
        return None
    try:
        lista = await hogar_router.conectados()
        router_ok = True
    except Exception:  # noqa: BLE001
        lista, router_ok = [], False
    por_mac = {hogar_router.mac_completa(c["mac"]): c for c in lista}
    vistos, presentes = f["vistos"], set()
    for m in a["moviles"]:
        if m["mac"] in por_mac:
            presentes.add(m["mac"])
            m["ip"] = por_mac[m["mac"]].get("ip") or m.get("ip", "")
        elif await asyncio.to_thread(_responde, m.get("ip", "")):
            presentes.add(m["mac"])
    for mac in presentes:
        vistos[mac] = ahora
    await asyncio.to_thread(_guardar, vistos=vistos, ajustes=a)
    alguien = bool(presentes)
    if not router_ok and not alguien:
        return None   # sin router no se puede afirmar que no hay nadie
    # Un móvil que nunca se ha visto cuenta desde que se activó la vigilancia (no como «fuera desde siempre»).
    todos_fuera = all(ahora - vistos.get(m["mac"], f["desde"] or ahora) >= a["minutos"] * 60 for m in a["moviles"])
    if f["estado"] == "casa" and not alguien and todos_fuera:
        fallidas = await _poner_privacidad(a["camaras"], False)
        await asyncio.to_thread(_guardar, estado="fuera", desde=ahora)
        texto = "No queda nadie en casa: he destapado la cámara para que vigile."
        if fallidas:
            texto += " Ojo: alguna cámara no ha respondido."
        await avisos.emitir("vigilancia", "aviso", texto, "hogar")
        return "fuera"
    if f["estado"] == "fuera" and alguien:
        quien = next(m["nombre"] for m in a["moviles"] if m["mac"] in presentes)
        fallidas = await _poner_privacidad(a["camaras"], True)
        await asyncio.to_thread(_guardar, estado="casa", desde=ahora)
        texto = f"Ya hay alguien en casa ({quien}): he vuelto a tapar la cámara."
        if fallidas:
            texto += " Ojo: alguna cámara no ha respondido."
        await avisos.emitir("vigilancia", "aviso", texto, "hogar")
        return "casa"
    return None


async def bucle() -> None:
    await asyncio.sleep(60)
    while True:
        try:
            await ciclo()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Fallo en la vigilancia automática")
        await asyncio.sleep(INTERVALO_S)
