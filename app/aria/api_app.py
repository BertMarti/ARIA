"""API de vinculación y resumen de la aplicación nativa."""
import asyncio
import hashlib
import ipaddress
import json
import math
import time
from contextlib import closing
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from . import agenda, avisos, briefing, config, db, dispositivos_app, invitados, premium, services, shield, ubicacion, vpn

router = APIRouter()
_lim_crear = avisos.Limitador(5, 3600)
_lim_resumen = avisos.Limitador(60, 3600)
_lim_fallos = avisos.Limitador(5, 3600)


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


@router.post("/api/app/dispositivos")
async def crear(request: Request):
    u = request.state.usuario
    if getattr(request.state, "vista", None) or await asyncio.to_thread(invitados.de, u["id"]):
        return JSONResponse({"error": "Esta cuenta no puede vincular dispositivos."}, status_code=403)
    if not _lim_crear.permitir(u["id"]):
        return JSONResponse({"error": "Demasiadas peticiones seguidas; espera un poco."}, status_code=429)
    d = await _json(request)
    if not isinstance(d.get("nombre", ""), str) or not d.get("nombre", "").strip() or len(d["nombre"].strip()) > 60:
        return JSONResponse({"error": "El nombre debe tener entre 1 y 60 caracteres."}, status_code=400)
    # ARIA Gratis: un móvil vinculado (avisos y widget); Premium: los que quieras, también el token de Atajos/Siri.
    if not premium.tiene("app_extra") and len(await asyncio.to_thread(dispositivos_app.listar, u["id"])) >= 1:
        return JSONResponse({"error": "Con ARIA Gratis puedes vincular un móvil. Hazte Premium para tener más.",
                             "premium": "app_extra"}, status_code=402)
    return await asyncio.to_thread(dispositivos_app.crear, u["id"], d["nombre"])


@router.get("/api/app/dispositivos")
async def listar(request: Request):
    return {"dispositivos": await asyncio.to_thread(dispositivos_app.listar, request.state.usuario["id"])}


@router.delete("/api/app/dispositivos/{ident:int}")
async def revocar(ident: int, request: Request):
    ok = await asyncio.to_thread(dispositivos_app.revocar, request.state.usuario["id"], ident)
    return {"ok": ok} if ok else JSONResponse({"error": "Dispositivo no encontrado."}, status_code=404)


@router.get("/api/app/resumen")
async def resumen(request: Request):
    u = request.state.usuario
    token = request.state.app_token
    if not _lim_resumen.permitir(hashlib.sha256(token.encode()).hexdigest()):
        return JSONResponse({"error": "Demasiadas peticiones seguidas; espera un poco."}, status_code=429)
    datos = await _datos_resumen(u)
    if request.query_params.get("formato") == "texto":
        return PlainTextResponse(_texto_resumen(datos), media_type="text/plain; charset=utf-8")
    return datos


def _recortar(valor, limite: int) -> str:
    return valor.strip()[:limite] if isinstance(valor, str) else ""


def _guardar_fallo(uid: int, datos: dict) -> tuple[dict, bool]:
    ahora = datos["cuando"] / 1000
    with closing(db._con()) as con, con:
        cur = con.execute(
            "INSERT INTO app_fallos (user_id, cuando, version, android, modelo, excepcion, traza) "
            "VALUES (?,?,?,?,?,?,?)",
            (uid, ahora, datos["version"], datos["android"], datos["modelo"], datos["excepcion"], datos["traza"]),
        )
        fila = {"id": cur.lastrowid, "user_id": uid, "cuando": ahora, **datos}
        con.execute("DELETE FROM app_fallos WHERE id NOT IN (SELECT id FROM app_fallos ORDER BY cuando DESC, id DESC LIMIT 50)")
        repetido = con.execute(
            "SELECT 1 FROM app_fallos WHERE excepcion=? AND version=? AND cuando>=? AND id<>? LIMIT 1",
            (datos["excepcion"], datos["version"], ahora - 86400, cur.lastrowid),
        ).fetchone() is not None
    return fila, repetido


@router.post("/api/app/fallos")
async def registrar_fallo(request: Request):
    u = request.state.usuario
    try:
        if int(request.headers.get("content-length", "0")) > 8192:
            return JSONResponse({"error": "El informe es demasiado grande."}, status_code=413)
    except ValueError:
        return JSONResponse({"error": "Cabecera de tamaño no válida."}, status_code=400)
    cuerpo = await request.body()
    if len(cuerpo) > 8192:
        return JSONResponse({"error": "El informe es demasiado grande."}, status_code=413)
    try:
        d = json.loads(cuerpo)
    except (TypeError, ValueError):
        return JSONResponse({"error": "Informe no válido."}, status_code=400)
    if (not isinstance(d, dict) or not isinstance(d.get("android"), int) or isinstance(d["android"], bool)
            or not isinstance(d.get("cuando"), (int, float)) or isinstance(d["cuando"], bool)
            or not math.isfinite(d["cuando"]) or d["cuando"] <= 0):
        return JSONResponse({"error": "Informe no válido."}, status_code=400)
    # La hora del cierre la pone el móvil: se acota a los últimos 30 días para que no descoloque la lista ni el deduplicado.
    ahora_ms = time.time() * 1000
    cuando = min(max(float(d["cuando"]), ahora_ms - 30 * 86400 * 1000), ahora_ms)
    datos = {"version": _recortar(d.get("version"), 100), "android": d["android"], "cuando": cuando,
             "modelo": _recortar(d.get("modelo"), 120), "excepcion": _recortar(d.get("excepcion"), 300),
             "traza": _recortar(d.get("traza"), 4000)}
    if not all(datos[k] for k in ("version", "modelo", "excepcion")) or not 0 <= datos["android"] <= 1000:
        return JSONResponse({"error": "Informe no válido."}, status_code=400)
    if not _lim_fallos.permitir(u["id"]):
        return JSONResponse({"error": "Demasiados informes; espera un poco."}, status_code=429)
    fallo, repetido = await asyncio.to_thread(_guardar_fallo, u["id"], datos)
    if not repetido:
        texto = f"La app de Android se ha cerrado (ARIA {datos['version']}, Android {datos['android']}): {datos['excepcion']}"
        await avisos.emitir("app", "aviso", texto, "ajustes")
    return {"ok": True, "id": fallo["id"]}


@router.get("/api/app/fallos")
async def listar_fallos(request: Request):
    def leer():
        with closing(db._con()) as con:
            return [dict(r) for r in con.execute(
                "SELECT id, user_id, cuando, version, android, modelo, excepcion, traza "
                "FROM app_fallos ORDER BY cuando DESC, id DESC LIMIT 50")]
    return {"fallos": await asyncio.to_thread(leer)}


def _direcciones_casa() -> list:
    """Direcciones de ARIA dentro de casa (o por la VPN): IP privadas y nombres .local/.lan. La IP de la LAN va
    primero porque no depende del DNS (con la VPN, «aria.local» puede no resolverse)."""
    def de_casa(h: str) -> bool:
        try:
            return ipaddress.ip_address(h).is_private and not ipaddress.ip_address(h).is_loopback
        except ValueError:
            return h.endswith((".local", ".lan")) and h.replace(".", "").replace("-", "").isalnum()
    hosts = sorted((h for h in config.HOSTS if de_casa(h)), key=lambda h: (h != config.LAN_IP.lower(), h))
    return [f"https://{h}/" for h in hosts][:5]


@router.get("/api/app/casa")
async def casa():
    """Plan B de la app de Android: si el operador bloquea Cloudflare (LaLiga), la app entra por estas direcciones,
    fiándose SOLO de su certificado si lo firma la autoridad de esta casa (el certificado raíz es público)."""
    ruta = config.DATA_DIR / "aria-certificado.crt"
    try:
        pem = await asyncio.to_thread(ruta.read_text, encoding="ascii")
    except (OSError, UnicodeDecodeError):
        pem = ""
    if "BEGIN CERTIFICATE" not in pem:
        return JSONResponse({"error": "Certificado de casa no disponible."}, status_code=404)
    return {"direcciones": _direcciones_casa(), "certificado": pem.strip()}


async def _datos_resumen(u: dict) -> dict:
    lim = await asyncio.to_thread(invitados.de, u["id"]) if u["rol"] != "admin" else None
    avisos_d = await asyncio.to_thread(avisos.listar, u["id"], 100)
    ahora = time.time()
    pendientes = [{"id": a["id"], "texto": a["texto"][:300], "severidad": a["severidad"], "ts": a["creado"]}
                  for a in avisos_d["avisos"] if not a["leido"]][:20]
    # El tiempo es el de casa (lleva el nombre del pueblo): un invitado solo lo ve si su acceso incluye Inicio.
    lugar = ubicacion._casa()
    tiempo_d = await briefing._tiempo(lugar) if lim is None or "inicio" in lim["secciones"] else None
    tiempo_mini = None if not tiempo_d else {"lugar": tiempo_d.get("ciudad"), "actual": tiempo_d.get("actual"),
                                             "min": tiempo_d.get("min"), "max": tiempo_d.get("max"),
                                             "cielo": tiempo_d.get("cielo")}
    proximo, proximos = None, []
    if lim is None or "agenda" in lim["secciones"]:
        desde = briefing.tiempo.ahora()
        eventos = await asyncio.to_thread(agenda.listar_eventos, u["id"], desde.isoformat(),
                                          (desde + timedelta(days=7)).isoformat())
        futuro = [e for e in eventos if e.get("inicio", "") >= desde.isoformat()]
        proximos = [{"titulo": e.get("titulo"), "inicio": e.get("inicio")} for e in futuro[:3]]   # widget de Agenda
        proximo = proximos[0] if proximos else None
    casa = await _casa() if u["rol"] == "admin" else None   # widget de Casa: solo quien administra la red
    hogar = await asyncio.to_thread(_hogar) if u["rol"] == "admin" else None   # widget de Hogar
    return {"avisos": pendientes, "tiempo": tiempo_mini, "proximo": proximo, "proximos": proximos, "casa": casa,
            "hogar": hogar, "generado": ahora}


def _hogar() -> dict:
    """Cámaras, luces y vigilancia con lo último que ARIA ya sabe (no despierta cámaras ni espera al router)."""
    from . import hogar_cache, hogar_vigilancia
    camaras = hogar_cache.ultimo("camaras") or []
    luces = hogar_cache.ultimo("luces") or []
    try:
        a = hogar_vigilancia.resumen(None)
        vig = {"activa": a["activa"], "estado": a["estado"]} if a["moviles"] else None
    except Exception:  # noqa: BLE001
        vig = None
    return {"camaras": len(camaras), "tapadas": sum(1 for c in camaras if c.get("privacidad")),
            "sin_respuesta": sum(1 for c in camaras if not c.get("en_linea")),
            "luces": len(luces), "luces_encendidas": sum(1 for x in luces if x.get("encendida")), "vigilancia": vig}


async def _casa() -> dict:
    """Anuncios bloqueados, VPN y servicios. Cada dato es opcional: si algo tarda o falla, el widget enseña el resto."""
    async def dato(corrutina):
        try:
            return await asyncio.wait_for(corrutina, 4)
        except Exception:
            return None
    s, clientes, servicios = await asyncio.gather(
        dato(shield.resumen()) if shield.configurado() else asyncio.sleep(0),
        dato(vpn.listar()) if vpn.configurado() else asyncio.sleep(0),
        dato(services.estado()))
    return {"anuncios": s.get("bloqueadas") if s else None, "porcentaje": s.get("porcentaje") if s else None,
            "bloqueo_activo": s.get("bloqueo_activo") if s else None,
            "vpn_conectados": sum(1 for c in clientes if c.get("conectado")) if isinstance(clientes, list) else None,
            "servicios_ok": all(x.get("estado") == "ok" for x in servicios.values()) if servicios else None}


def _texto_resumen(datos: dict) -> str:
    partes = []
    pendientes = datos["avisos"]
    if pendientes:
        primero = pendientes[0]["texto"].replace("\n", " ").strip()[:120]
        if len(pendientes[0]["texto"].replace("\n", " ").strip()) > 120:
            primero += "…"
        unidad = "aviso" if len(pendientes) == 1 else "avisos"
        partes.append(f"Tienes {len(pendientes)} {unidad} sin leer: {primero}{'' if primero.endswith(('.', '!', '?', '…')) else '.'}")
    tiempo_d = datos.get("tiempo")
    if tiempo_d:
        cielo = tiempo_d.get("cielo") or "sin descripción"
        partes.append(f"En {tiempo_d.get('lugar') or 'casa'} hace {tiempo_d.get('actual')} grados, {cielo}; máxima de {tiempo_d.get('max')}.")
    proximo = datos.get("proximo")
    if proximo:
        inicio = datetime.fromisoformat(proximo["inicio"].replace("Z", "+00:00")).astimezone(briefing.tiempo.zona())
        ahora = briefing.tiempo.ahora()
        dias = (inicio.date() - ahora.date()).days
        cuando = "hoy" if dias == 0 else "mañana" if dias == 1 else f"el {briefing.tiempo.DIAS[inicio.weekday()]}"
        partes.append(f"Tu próximo evento: {proximo.get('titulo') or 'sin título'}, {cuando} a las {inicio:%H:%M}.")
    return " ".join(partes) if partes else "Todo tranquilo: no tienes avisos."
