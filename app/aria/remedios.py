"""Acciones seguras y estados persistentes para los hallazgos de Seguridad."""
import hashlib
import re
import time
from contextlib import closing

from . import config, db, escaneo, red, registro, vpn

DIAS = (30, 90, 365)


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS hallazgos_estado (
            clave TEXT PRIMARY KEY, estado TEXT CHECK(estado IN ('aceptado','revisado')),
            motivo TEXT, huella TEXT, hasta REAL, user_id INTEGER, ts REAL)""")


def clave(h: dict) -> str:
    return hashlib.sha256(f"{h.get('tipo','')}|{h.get('ip') or ''}|{h.get('titulo','')}".encode()).hexdigest()[:16]


def huella(h: dict) -> str:
    return hashlib.sha256(str(h.get("detalle") or "").encode()).hexdigest()[:16]


def estado(h: dict) -> dict | None:
    with closing(db._con()) as con:
        r = con.execute("SELECT estado,motivo,hasta,huella FROM hallazgos_estado WHERE clave=?", (clave(h),)).fetchone()
    if not r or (r["hasta"] is not None and r["hasta"] <= time.time()) or r["huella"] != huella(h):
        return None
    return {"estado": r["estado"], "motivo": r["motivo"], "hasta": r["hasta"]}


def _guardar(k, h, motivo, dias, uid, estado_n):
    if not isinstance(motivo, str) or not 3 <= len(motivo.strip()) <= 200:
        raise ValueError("El motivo debe tener entre 3 y 200 caracteres.")
    if dias not in DIAS:
        raise ValueError("La duración debe ser de 30, 90 o 365 días.")
    ahora = time.time()
    with closing(db._con()) as con, con:
        con.execute("INSERT OR REPLACE INTO hallazgos_estado VALUES (?,?,?,?,?,?,?)",
                    (k, estado_n, motivo.strip(), h, ahora + dias * 86400, uid, ahora))


def aceptar(k, h, motivo, dias=90, uid=None):
    _guardar(k, h, motivo, dias, uid, "aceptado")


def revisar(k, h, motivo="Coincidencia revisada", dias=90, uid=None):
    _guardar(k, h, motivo, dias, uid, "revisado")


def reabrir(k) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM hallazgos_estado WHERE clave=?", (k,)).rowcount > 0


def _accion(texto, ident, peligro=False):
    return {"id": ident, "texto": texto, "peligro": peligro}


def remedio(h: dict) -> dict:
    tipo, ip = h.get("tipo"), h.get("ip")
    m = re.search(r"Puerto\s+(5900|1900|5000|5431)", h.get("detalle") or "")
    puerto = int(m.group(1)) if m else None
    if tipo == "servicio_riesgo" and ip == config.LAN_IP and puerto == 5900:
        return {"modo": "guia", "acciones": [], "pasos": [
            "Usas Raspberry Pi Connect, que lleva su propio VNC por un canal cifrado y NO usa el puerto 5900.",
            "Desactiva el VNC clásico: sudo raspi-config → Interface Options → VNC → No (o sudo systemctl disable --now wayvnc).",
            "Pulsa “Ya está, compruébalo”."], "comprobar": True}
    if tipo == "cve":
        texto = (h.get("detalle") or "").lower()
        if ip == config.LAN_IP and ("osv" in texto or "debian" in texto):
            return {"modo": "decidir", "acciones": [_accion("Marcar como revisado", "revisado")], "pasos": [
                "La Raspberry instala sola las actualizaciones de seguridad cada día (unattended-upgrades).",
                "Los avisos de Debian sin puntuación suelen estar ya corregidos en la versión de Debian o ser menores."], "comprobar": False}
        return {"modo": "guia", "acciones": [_accion("Marcar como revisado", "revisado")], "pasos": [
            "Abre la app Deco/Tether de TP-Link → Más → Sistema → Actualización de firmware en cada nodo.",
            "Muchas coincidencias de NVD son por número de versión y no afectan al servicio expuesto."], "comprobar": False}
    if tipo == "router" or (tipo == "servicio_riesgo" and ip == config.ROUTER_IP and puerto in (1900, 5000, 5431)):
        return {"modo": "guia", "acciones": [_accion("Aceptar riesgo", "aceptar")], "pasos": [
            "Si no juegas en consola online ni usas apps que lo pidan, desactívalo: app de TP-Link → Más → Avanzado → NAT → UPnP."], "comprobar": True}
    if tipo == "panel_admin":
        return {"modo": "guia", "acciones": [_accion("Aceptar riesgo", "aceptar")], "pasos": [
            "Cambia la contraseña por defecto y desactiva la gestión remota o el acceso desde la nube si no lo usas."], "comprobar": False}
    if tipo == "dispositivo_desconocido":
        ips = re.findall(r"(\d{1,3}(?:\.\d{1,3}){3})", h.get("detalle") or "")
        return {"modo": "decidir", "acciones": [_accion(f"Es mío ({x})", f"conocido:{x}") for x in dict.fromkeys(ips)], "pasos": [
            "Marca aquí tus dispositivos; los demás se gestionan desde Red."], "comprobar": False}
    if tipo == "vpn_sin_uso":
        return {"modo": "decidir", "acciones": [_accion("Desactivar peer", "desactivar_peer", True), _accion("Aceptar riesgo", "aceptar")], "pasos": [
            "Si no lo necesitas ahora, puedes desactivarlo. Motivo sugerido: «Se activa solo cuando lo uso»."], "comprobar": False}
    return {"modo": "guia", "acciones": [_accion("Aceptar riesgo", "aceptar")], "pasos": [h.get("recomendacion") or "Revisa este hallazgo en la red."], "comprobar": False}


async def aplicar(h, accion, uid, extra=None):
    extra = extra or {}
    if accion.startswith("conocido:"):
        ip = accion.split(":", 1)[1]
        k = red.buscar_clave(ip)
        if not k or not red.marcar_conocido(k, True):
            raise ValueError("Dispositivo no encontrado.")
        texto = f"Dispositivo {ip} marcado como conocido."
    elif accion == "desactivar_peer":
        nombre = h.get("titulo", "").split(":", 1)[-1].strip()
        peer = next((p for p in await vpn.listar() if p.get("nombre") == nombre), None)
        if not peer:
            raise ValueError("Peer no encontrado.")
        await vpn.activar(peer.get("id"), False)
        texto = f"Peer {nombre} desactivado."
    elif accion in ("revisado", "aceptar"):
        if accion == "aceptar" and not extra.get("motivo"):
            raise ValueError("Aceptar el riesgo exige un motivo.")
        motivo = extra.get("motivo") or "Coincidencia revisada"
        dias = extra.get("dias", 90)
        if accion == "revisado": revisar(clave(h), huella(h), motivo, dias, uid)
        else: aceptar(clave(h), huella(h), motivo, dias, uid)
        texto = "Hallazgo marcado como revisado." if accion == "revisado" else "Riesgo aceptado temporalmente."
    else:
        raise ValueError("Acción no permitida.")
    with registro.origen("seguridad"):
        registro.anotar(uid, "admin", "seguridad", accion, {"clave": clave(h)}, True, texto, 0)
    return texto


async def comprobar(h):
    escaneo.solicitar("rapido", origen="seguridad")
    return "Escaneo rápido en marcha; el siguiente informe comprobará si desaparece."
