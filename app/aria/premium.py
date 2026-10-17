"""Licencias locales de ARIA Premium.

La licencia se verifica sin red. En modo prueba la comprobación está desactivada
por defecto para que ninguna instalación existente pierda funciones.
"""
import base64
import json
import secrets
import time
from contextlib import closing
from datetime import date, datetime
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from . import config, db

CLAVE_PUBLICA_B64 = "jEohKKZPdKdKhueY8ZhfXNSnqiHEAwv6ssRIcUx+KbY="   # pública; la privada vive solo fuera de git
FUNCIONES = {
    "hud": "Modo HUD", "cerebro": "Cerebro", "tele": "Enviar a la tele",
    "documentos_extra": "Documentos ampliados", "finanzas_avanzadas": "Finanzas avanzadas",
    "remedios": "Arreglar lo que ARIA puede", "automatizaciones_extra": "Automatizaciones extra",
    "usuarios_extra": "Usuarios extra", "app_extra": "Widget, atajos y Siri", "vpn_extra": "HEIMDALL ampliado",
}
LIMITES_GRATIS = {"automatizaciones": 3, "documentos": 20, "usuarios": 2}
_PRUEBA_DIAS = 14
_GRACIA_DIAS = 21


class PremiumError(ValueError):
    pass


class PremiumRequired(Exception):
    def __init__(self, funcion: str):
        self.funcion = funcion


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS premium (
            id INTEGER PRIMARY KEY CHECK(id=1), licencia TEXT, prueba_inicio REAL,
            instalacion TEXT NOT NULL)""")
        con.execute("INSERT OR IGNORE INTO premium(id, instalacion) VALUES(1, ?)", (secrets.token_urlsafe(18),))


def _fila():
    iniciar()
    with closing(db._con()) as con:
        return con.execute("SELECT * FROM premium WHERE id=1").fetchone()


def _b64(texto: str) -> bytes:
    if not isinstance(texto, str) or not texto or len(texto) > 2048:
        raise PremiumError("La licencia no es válida.")
    try:
        return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))
    except (ValueError, TypeError):
        raise PremiumError("La licencia no es válida.") from None


def _hoy() -> date:
    return datetime.now(ZoneInfo(config.TZ)).date()   # la fecha de casa, no la del contenedor (UTC)


def _payload(texto: str) -> dict:
    if len(texto.encode("utf-8")) > 2048:
        raise PremiumError("La licencia es demasiado grande.")
    partes = texto.split(".")
    if len(partes) != 2:
        raise PremiumError("La licencia no es válida.")
    crudo, firma = _b64(partes[0]), _b64(partes[1])
    try:
        clave = base64.b64decode(CLAVE_PUBLICA_B64, validate=True)
        Ed25519PublicKey.from_public_bytes(clave).verify(firma, crudo)
        datos = json.loads(crudo.decode("utf-8"))
    except Exception:
        raise PremiumError("La firma de la licencia no es válida.") from None
    if not isinstance(datos, dict) or datos.get("v") != 1 or datos.get("plan") != "premium":
        raise PremiumError("La licencia no es válida.")
    requeridos = {"v", "id", "plan", "emitida", "caduca", "instalacion"}
    if set(datos) != requeridos or not isinstance(datos["id"], str) or not datos["id"] \
            or datos["instalacion"] is not None and not isinstance(datos["instalacion"], str):
        raise PremiumError("La licencia no es válida.")
    try:
        date.fromisoformat(datos["emitida"]); date.fromisoformat(datos["caduca"])
    except (TypeError, ValueError):
        raise PremiumError("Las fechas de la licencia no son válidas.") from None
    return datos


def instalar_licencia(texto: str) -> dict:
    datos = _payload(texto)
    fila = _fila()
    if datos["instalacion"] is not None and datos["instalacion"] != fila["instalacion"]:
        raise PremiumError("La licencia pertenece a otra instalación.")
    with closing(db._con()) as con, con:
        con.execute("UPDATE premium SET licencia=? WHERE id=1", (texto,))
    return estado()


def quitar_licencia() -> dict:
    with closing(db._con()) as con, con:
        con.execute("UPDATE premium SET licencia=NULL WHERE id=1")
    return estado()


def empezar_prueba() -> dict:
    fila = _fila()
    if fila["prueba_inicio"] is not None:
        raise PremiumError("La prueba gratuita ya se ha utilizado en esta instalación.")
    with closing(db._con()) as con, con:
        con.execute("UPDATE premium SET prueba_inicio=? WHERE id=1", (time.time(),))
    return estado()


def _estado_real(fila) -> tuple[str, int | None]:
    hoy = _hoy()
    if fila["licencia"]:
        try:
            p = _payload(fila["licencia"])
            caduca = date.fromisoformat(p["caduca"])
            dias = (caduca - hoy).days
            if dias >= 0: return "premium", dias
            if dias >= -_GRACIA_DIAS: return "gracia", 0
        except PremiumError:
            pass
        return "caducada", 0
    if fila["prueba_inicio"] is not None:
        inicio = datetime.fromtimestamp(fila["prueba_inicio"], ZoneInfo(config.TZ)).date()
        transcurridos = (_hoy() - inicio).days
        dias = _PRUEBA_DIAS - transcurridos
        return ("prueba", dias) if dias > 0 else ("caducada", 0)
    return "gratis", None


def estado() -> dict:
    fila = _fila()
    real, dias = _estado_real(fila)
    activo = real in ("premium", "prueba", "gracia")
    return {"estado": real, "exigir": config.PREMIUM_EXIGIR, "modo_prueba": not config.PREMIUM_EXIGIR,
            "funciones": {k: (True if not config.PREMIUM_EXIGIR else activo) for k in FUNCIONES},
            "nombres": FUNCIONES, "limites": {k: limite(k) for k in LIMITES_GRATIS}, "dias_restantes": dias}


def tiene(funcion: str) -> bool:
    return funcion in FUNCIONES and (not config.PREMIUM_EXIGIR or _estado_real(_fila())[0] in ("premium", "prueba", "gracia"))


def limite(nombre: str) -> int | None:
    return None if tiene("automatizaciones_extra") else LIMITES_GRATIS.get(nombre)


def requiere(funcion: str):
    def dependencia():
        if not tiene(funcion):
            raise PremiumRequired(funcion)
    return dependencia
