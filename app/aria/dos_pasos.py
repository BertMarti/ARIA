"""Verificación en dos pasos (TOTP, RFC 6238) para el acceso con contraseña de casa.

- Compatible con Google Authenticator, Aegis, 1Password, Microsoft Authenticator…: 6 dígitos cada 30 s, SHA-1.
- El secreto se guarda cifrado con una clave derivada de ARIA_SECRET (una copia de la base de datos sola no basta).
- Antirrepetición: un código ya usado no vale otra vez. Se acepta ±30 s de desfase de reloj.
- 8 códigos de recuperación de un solo uso (solo se guarda su huella).
- El acceso por Cloudflare Access (SSO) no pasa por aquí: Access ya tiene su propio segundo factor.

Si alguien pierde el móvil y los códigos: `docker compose exec app python -m aria.dos_pasos desactivar <email>`.
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import sys
import time
from contextlib import closing
from urllib.parse import quote

from . import config, db

PASO = 30
DIGITOS = 6
N_RECUPERACION = 8


class DosPasosError(Exception):
    """Error legible para la interfaz."""


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS dos_pasos (
            user_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE, secreto TEXT NOT NULL,
            activo INTEGER NOT NULL DEFAULT 0, ultimo_paso INTEGER NOT NULL DEFAULT 0,
            recuperacion TEXT NOT NULL DEFAULT '[]', creado REAL NOT NULL)""")


# --- Cifrado del secreto (flujo HMAC-SHA256 con la clave de ARIA; el secreto mide 20 bytes) ---
def _flujo(uid: int, n: int) -> bytes:
    return hmac.new(config.SECRET.encode(), f"dos-pasos:{uid}".encode(), hashlib.sha256).digest()[:n]


def _cifrar(uid: int, crudo: bytes) -> str:
    return base64.b64encode(bytes(a ^ b for a, b in zip(crudo, _flujo(uid, len(crudo))))).decode()


def _descifrar(uid: int, guardado: str) -> bytes:
    c = base64.b64decode(guardado)
    return bytes(a ^ b for a, b in zip(c, _flujo(uid, len(c))))


# --- TOTP ---
def codigo(secreto: bytes, paso: int) -> str:
    h = hmac.new(secreto, struct.pack(">Q", paso), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITOS).zfill(DIGITOS)


def _paso(ahora: float | None = None) -> int:
    return int((time.time() if ahora is None else ahora) // PASO)


def _fila(uid: int):
    with closing(db._con()) as con:
        return con.execute("SELECT * FROM dos_pasos WHERE user_id=?", (uid,)).fetchone()


def activo(uid: int) -> bool:
    r = _fila(uid)
    return bool(r and r["activo"])


def _huella(c: str) -> str:
    return hashlib.sha256(("rec:" + c.replace("-", "").lower()).encode()).hexdigest()


def preparar(uid: int, cuenta: str) -> dict:
    """Secreto nuevo (aún sin activar). Devuelve el secreto en base32 y el enlace otpauth:// para el QR."""
    if activo(uid):
        raise DosPasosError("La verificación en dos pasos ya está activada.")
    crudo = secrets.token_bytes(20)
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO dos_pasos (user_id, secreto, activo, creado) VALUES (?,?,0,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET secreto=excluded.secreto, activo=0, ultimo_paso=0, "
                    "recuperacion='[]', creado=excluded.creado", (uid, _cifrar(uid, crudo), time.time()))
    b32 = base64.b32encode(crudo).decode().rstrip("=")
    etiqueta = quote(f"ARIA:{cuenta}")
    return {"secreto": " ".join(b32[i:i + 4] for i in range(0, len(b32), 4)),
            "uri": f"otpauth://totp/{etiqueta}?secret={b32}&issuer=ARIA&digits={DIGITOS}&period={PASO}"}


def _comprobar_totp(uid: int, r, entrada: str, ahora: float | None) -> bool:
    entrada = "".join(ch for ch in str(entrada) if ch.isdigit())
    if len(entrada) != DIGITOS:
        return False
    secreto, actual = _descifrar(uid, r["secreto"]), _paso(ahora)
    for p in (actual - 1, actual, actual + 1):
        if p > r["ultimo_paso"] and hmac.compare_digest(codigo(secreto, p), entrada):
            with closing(db._con()) as con, con:
                con.execute("UPDATE dos_pasos SET ultimo_paso=? WHERE user_id=?", (p, uid))
            return True
    return False


def activar(uid: int, entrada: str, ahora: float | None = None) -> list[str]:
    """Confirma con un código del móvil y devuelve los códigos de recuperación (se muestran una sola vez)."""
    r = _fila(uid)
    if not r:
        raise DosPasosError("Primero genera el código QR.")
    if r["activo"]:
        raise DosPasosError("La verificación en dos pasos ya está activada.")
    if not _comprobar_totp(uid, r, entrada, ahora):
        raise DosPasosError("El código no es correcto. Revisa la hora del móvil y vuelve a intentarlo.")
    recuperacion = ["-".join(secrets.token_hex(2) for _ in range(3)) for _ in range(N_RECUPERACION)]
    with closing(db._con()) as con, con:
        con.execute("UPDATE dos_pasos SET activo=1, recuperacion=? WHERE user_id=?",
                    (json.dumps([_huella(c) for c in recuperacion]), uid))
    return recuperacion


def verificar(uid: int, entrada: str, ahora: float | None = None) -> bool:
    """Código TOTP o, si no, un código de recuperación (que se gasta)."""
    r = _fila(uid)
    if not r or not r["activo"]:
        return False
    if _comprobar_totp(uid, r, entrada, ahora):
        return True
    limpio = str(entrada or "").strip().lower()
    if len(limpio.replace("-", "")) == 12:
        huellas = json.loads(r["recuperacion"] or "[]")
        h = _huella(limpio)
        if h in huellas:
            huellas.remove(h)
            with closing(db._con()) as con, con:
                con.execute("UPDATE dos_pasos SET recuperacion=? WHERE user_id=?", (json.dumps(huellas), uid))
            return True
    return False


def quedan_recuperacion(uid: int) -> int:
    r = _fila(uid)
    return len(json.loads(r["recuperacion"] or "[]")) if r else 0


def desactivar(uid: int, entrada: str | None = None, forzar: bool = False) -> bool:
    if not forzar and not verificar(uid, entrada or ""):
        raise DosPasosError("El código no es correcto.")
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM dos_pasos WHERE user_id=?", (uid,)).rowcount > 0


if __name__ == "__main__":   # rescate: python -m aria.dos_pasos desactivar <email o usuario>
    from . import usuarios
    if len(sys.argv) == 3 and sys.argv[1] == "desactivar":
        u = usuarios.por_identificador(sys.argv[2])
        if not u:
            sys.exit("No existe ese usuario.")
        print("Desactivada." if desactivar(u["id"], forzar=True) else "No la tenía activada.")
    else:
        sys.exit("Uso: python -m aria.dos_pasos desactivar <email o usuario>")
