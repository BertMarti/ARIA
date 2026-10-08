"""Notificaciones push del navegador y del móvil (Web Push con VAPID, RFC 8030/8291/8292).

Implementación mínima con `cryptography` (ya viene con PyJWT[crypto]): cifrado aes128gcm del mensaje y
cabecera VAPID firmada con ES256. Las claves VAPID salen de .env (VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY,
las genera install.sh); si faltan, se generan una vez en data/vapid.json (0600).

Seguridad: el servidor hace POST a la URL de la suscripción, así que solo se aceptan endpoints HTTPS de los
servicios push conocidos (Google, Mozilla, Apple, Microsoft): nada de URL arbitrarias (SSRF). Las
suscripciones caducadas (404/410) se borran solas.

    python -m aria.push --claves     # imprime un par de claves VAPID nuevo (formato .env)
"""
import base64
import json
import logging
import os
import struct
import sys
import time
from contextlib import closing
from urllib.parse import urlparse

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config, db

log = logging.getLogger("aria.push")

MAX_SUSCRIPCIONES = 10          # por usuario
MAX_NOMBRE = 40
TTL_S = 12 * 3600
# Servicios push admitidos (sufijos de host). Chrome/Edge/Android -> FCM, Firefox -> Mozilla, Safari/iOS -> Apple.
HOSTS_PUSH = ("fcm.googleapis.com", "android.googleapis.com", "push.services.mozilla.com",
              "updates.push.services.mozilla.com", "push.apple.com", "notify.windows.com")


class PushError(Exception):
    """Error legible (en español)."""


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def de_b64u(s: str) -> bytes:
    s = str(s or "").strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# --- Claves VAPID -----------------------------------------------------------------------------------
def generar_claves() -> tuple[str, str]:
    """(pública sin comprimir en base64url, privada de 32 bytes en base64url)."""
    k = ec.generate_private_key(ec.SECP256R1())
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64u(pub), b64u(k.private_numbers().private_value.to_bytes(32, "big"))


_claves: dict = {}


def claves() -> tuple[str, str]:
    if _claves.get("par"):
        return _claves["par"]
    pub, priv = config.VAPID_PUBLIC_KEY, config.VAPID_PRIVATE_KEY
    if not (pub and priv):
        ruta = config.DATA_DIR / "vapid.json"
        try:
            d = json.loads(ruta.read_text())
            pub, priv = d["publica"], d["privada"]
        except (OSError, ValueError, KeyError):
            pub, priv = generar_claves()
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            ruta.write_text(json.dumps({"publica": pub, "privada": priv}))
            ruta.chmod(0o600)
    _claves["par"] = (pub, priv)
    return pub, priv


def _privada() -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(de_b64u(claves()[1]), "big"), ec.SECP256R1())


def cabecera_vapid(endpoint: str, ahora: float | None = None) -> str:
    u = urlparse(endpoint)
    token = jwt.encode({"aud": f"{u.scheme}://{u.netloc}", "exp": int((ahora or time.time()) + 12 * 3600),
                        "sub": config.VAPID_SUBJECT}, _privada(), algorithm="ES256")
    return f"vapid t={token}, k={claves()[0]}"


# --- Cifrado aes128gcm (RFC 8291) -----------------------------------------------------------------------
def _hmac(clave: bytes, datos: bytes) -> bytes:
    h = hmac.HMAC(clave, hashes.SHA256())
    h.update(datos)
    return h.finalize()


def cifrar(mensaje: bytes, p256dh: str, auth: str, sal: bytes | None = None,
           efimera: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    ua_pub = de_b64u(p256dh)
    secreto_auth = de_b64u(auth)
    if len(ua_pub) != 65 or len(secreto_auth) < 16:
        raise PushError("Suscripción no válida.")
    efimera = efimera or ec.generate_private_key(ec.SECP256R1())
    as_pub = efimera.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    compartido = efimera.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
    prk_clave = _hmac(secreto_auth, compartido)
    ikm = _hmac(prk_clave, b"WebPush: info\x00" + ua_pub + as_pub + b"\x01")
    sal = sal or os.urandom(16)
    prk = _hmac(sal, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    cifrado = AESGCM(cek).encrypt(nonce, mensaje + b"\x02", None)
    return sal + struct.pack(">I", 4096) + bytes([len(as_pub)]) + as_pub + cifrado


# --- Suscripciones ------------------------------------------------------------------------------------------
def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS push_suscripciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                endpoint TEXT NOT NULL UNIQUE, p256dh TEXT NOT NULL, auth TEXT NOT NULL,
                nombre TEXT NOT NULL, creado REAL NOT NULL, ultimo_envio REAL);
            CREATE INDEX IF NOT EXISTS idx_push_user ON push_suscripciones(user_id);
        """)


def endpoint_valido(endpoint) -> bool:
    if not isinstance(endpoint, str) or len(endpoint) > 1024:
        return False
    u = urlparse(endpoint)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and not u.username and not u.port and any(
        host == h or host.endswith("." + h) for h in HOSTS_PUSH)


def validar(sub) -> dict:
    if not isinstance(sub, dict) or not isinstance(sub.get("keys"), dict):
        raise PushError("Suscripción no válida.")
    ep, k = sub.get("endpoint"), sub["keys"]
    if not endpoint_valido(ep):
        raise PushError("Ese servicio de notificaciones no está admitido.")
    try:
        if len(de_b64u(k.get("p256dh"))) != 65 or len(de_b64u(k.get("auth"))) < 16:
            raise ValueError
    except (ValueError, TypeError):
        raise PushError("Las claves de la suscripción no son válidas.") from None
    return {"endpoint": ep, "p256dh": k["p256dh"], "auth": k["auth"]}


def _publica(r) -> dict:
    return {"id": r["id"], "nombre": r["nombre"], "creado": r["creado"], "ultimo_envio": r["ultimo_envio"],
            "servicio": (urlparse(r["endpoint"]).hostname or "").split(".", 1)[-1]}


def suscribir(uid: int, sub, nombre) -> dict:
    s = validar(sub)
    nombre = " ".join(str(nombre or "").split())[:MAX_NOMBRE] or "Este dispositivo"
    with closing(db._con()) as con, con:
        previa = con.execute("SELECT user_id FROM push_suscripciones WHERE endpoint=?", (s["endpoint"],)).fetchone()
        if previa is None and con.execute("SELECT COUNT(*) FROM push_suscripciones WHERE user_id=?",
                                          (uid,)).fetchone()[0] >= MAX_SUSCRIPCIONES:
            raise PushError(f"Como mucho {MAX_SUSCRIPCIONES} dispositivos; quita alguno.")
        # El mismo navegador (mismo endpoint) pasa a ser del usuario que se suscribe ahora.
        con.execute("INSERT INTO push_suscripciones (user_id, endpoint, p256dh, auth, nombre, creado) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(endpoint) DO UPDATE SET user_id=excluded.user_id, p256dh=excluded.p256dh, "
                    "auth=excluded.auth, nombre=excluded.nombre",
                    (uid, s["endpoint"], s["p256dh"], s["auth"], nombre, time.time()))
        r = con.execute("SELECT * FROM push_suscripciones WHERE endpoint=?", (s["endpoint"],)).fetchone()
    return _publica(r)


def listar(uid: int) -> list:
    with closing(db._con()) as con:
        return [_publica(r) for r in con.execute(
            "SELECT * FROM push_suscripciones WHERE user_id=? ORDER BY creado", (uid,))]


def borrar(uid: int, sid: int) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM push_suscripciones WHERE id=? AND user_id=?", (sid, uid)).rowcount > 0


def _de_usuario(uid: int) -> list:
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute("SELECT * FROM push_suscripciones WHERE user_id=?", (uid,))]


def _resultado(sid: int, estado: int) -> None:
    with closing(db._con()) as con, con:
        if estado in (404, 410):
            con.execute("DELETE FROM push_suscripciones WHERE id=?", (sid,))
        elif 200 <= estado < 300:
            con.execute("UPDATE push_suscripciones SET ultimo_envio=? WHERE id=?", (time.time(), sid))


# --- Envío ----------------------------------------------------------------------------------------------------
async def enviador_http(endpoint: str, cabeceras: dict, cuerpo: bytes) -> int:
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as c:
        r = await c.post(endpoint, headers=cabeceras, content=cuerpo)
    return r.status_code


enviador = enviador_http  # se sustituye en las pruebas


async def enviar(uid: int, titulo: str, cuerpo: str, url: str = "/", etiqueta: str = "aria",
                 urgencia: str = "normal") -> dict:
    """Envía a todos los dispositivos del usuario. Devuelve {enviados, borrados, fallidos}."""
    import asyncio
    datos = json.dumps({"titulo": titulo[:80], "cuerpo": cuerpo[:400], "url": url if url.startswith("/") else "/",
                        "etiqueta": etiqueta[:40]}, ensure_ascii=False).encode()
    res = {"enviados": 0, "borrados": 0, "fallidos": 0}
    for s in await asyncio.to_thread(_de_usuario, uid):
        try:
            cuerpo_cif = cifrar(datos, s["p256dh"], s["auth"])
            cab = {"Authorization": cabecera_vapid(s["endpoint"]), "Content-Encoding": "aes128gcm",
                   "Content-Type": "application/octet-stream", "TTL": str(TTL_S), "Urgency": urgencia}
            estado = await enviador(s["endpoint"], cab, cuerpo_cif)
        except (httpx.HTTPError, PushError, ValueError) as e:
            log.warning("Push fallido (%s)", type(e).__name__)
            res["fallidos"] += 1
            continue
        await asyncio.to_thread(_resultado, s["id"], estado)
        if estado in (404, 410):
            res["borrados"] += 1
        elif 200 <= estado < 300:
            res["enviados"] += 1
        else:
            res["fallidos"] += 1
    return res


async def canal(uid: int, aviso: dict) -> bool:
    """Canal del motor de avisos."""
    t = aviso["tipo"]
    titulo = ("ARIA · Recordatorio" if t == "recordatorio" else "ARIA · Buenos días" if t == "resumen"
              else "ARIA · Importante" if aviso["severidad"] == "grave" else "ARIA")
    url = "/#" + aviso["enlace"] if aviso.get("enlace") else "/"
    r = await enviar(uid, titulo, aviso["texto"], url, f"aria-{aviso['tipo']}",
                     "high" if aviso["severidad"] == "grave" or aviso["tipo"] == "recordatorio" else "normal")
    return r["enviados"] > 0


if __name__ == "__main__":  # pragma: no cover
    if "--claves" in sys.argv:
        pub, priv = generar_claves()
        print(f"VAPID_PUBLIC_KEY={pub}\nVAPID_PRIVATE_KEY={priv}")
