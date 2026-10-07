"""Sesion firmada, comparacion en tiempo constante y limitador de intentos."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import config

COOKIE = "aria_session"
MAX_AGE = 7 * 24 * 3600
VENTANA = 300      # segundos
MAX_FALLOS = 5

MIN_PASSWORD = 10
_N, _R, _P = 2 ** 14, 8, 1

_ser = URLSafeTimedSerializer(config.SECRET or "sin-secreto", salt="aria-session")
_fallos: dict = {}
AUTH_FILE = config.DATA_DIR / "auth.json"


# --- Hash de contraseña (scrypt con sal) ---
def hashear(password: str) -> str:
    sal = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    b = lambda x: base64.b64encode(x).decode()  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b(sal)}${b(h)}"


def verificar_hash(password: str, almacenado: str) -> bool:
    try:
        alg, n, r, p, sal, esperado = almacenado.split("$")
        if alg != "scrypt":
            return False
        sal_b, esp_b = base64.b64decode(sal), base64.b64decode(esperado)
        h = hashlib.scrypt(password.encode(), salt=sal_b, n=int(n), r=int(r), p=int(p), dklen=len(esp_b))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(h, esp_b)


def igual(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


HASH_FALSO = hashear("aria-hash-falso")  # para gastar el mismo tiempo cuando el usuario no existe


def leer_legado() -> dict:
    """data/auth.json del admin único anterior (solo se lee al migrar a la tabla de usuarios)."""
    try:
        d = json.loads(AUTH_FILE.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def habilitado() -> bool:
    return len(config.SECRET) >= 16


def crear_sesion(usuario: dict) -> str:
    """Cookie firmada con el id del usuario y su versión de sesión (cambia al cambiar la contraseña o desactivarlo)."""
    return _ser.dumps({"u": usuario["id"], "v": usuario["version"]})


def sesion_usuario(token: str | None) -> dict | None:
    """Usuario activo al que pertenece la cookie, o None."""
    if not token or not habilitado():
        return None
    try:
        datos = _ser.loads(token, max_age=MAX_AGE)
    except BadSignature:
        return None
    if not isinstance(datos, dict):
        return None
    from . import usuarios  # import tardío: usuarios depende de este módulo
    uid = datos.get("u")
    if isinstance(uid, str) and config.USER and uid == config.USER:
        # Cookie de antes de la migración: era la del admin único.
        u = usuarios.por_identificador(config.USER)
    else:
        u = usuarios.por_id(uid)
    if not u or not u["activo"] or datos.get("v", 1) != u["version"]:
        return None
    return u


def bloqueado(ip: str) -> int:
    """Segundos restantes de bloqueo (0 si no esta bloqueado)."""
    ahora = time.time()
    f = [t for t in _fallos.get(ip, []) if ahora - t < VENTANA]
    _fallos[ip] = f
    if len(f) >= MAX_FALLOS:
        return int(VENTANA - (ahora - f[0])) + 1
    return 0


def registrar_fallo(ip: str) -> None:
    _fallos.setdefault(ip, []).append(time.time())
    if len(_fallos) > 1000:  # evita crecimiento sin limite
        for k in [k for k, v in _fallos.items() if not v or time.time() - v[-1] > VENTANA]:
            _fallos.pop(k, None)


def limpiar_fallos(ip: str) -> None:
    _fallos.pop(ip, None)
