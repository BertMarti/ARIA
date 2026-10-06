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


def _leer() -> dict:
    try:
        d = json.loads(AUTH_FILE.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar(d: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = AUTH_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f)
    os.replace(tmp, AUTH_FILE)


def version_sesion() -> int:
    v = _leer().get("version", 1)
    return v if isinstance(v, int) else 1


def cambiar_password(actual: str, nueva: str, repetida: str) -> str | None:
    """Devuelve un mensaje de error (en español) o None si se cambió."""
    if not password_ok(actual):
        return "La contraseña actual no es correcta."
    if nueva != repetida:
        return "Las contraseñas nuevas no coinciden."
    if len(nueva) < MIN_PASSWORD:
        return f"La contraseña nueva debe tener al menos {MIN_PASSWORD} caracteres."
    if nueva == actual:
        return "La contraseña nueva debe ser distinta de la actual."
    _guardar({"hash": hashear(nueva), "version": version_sesion() + 1})
    return None


def password_ok(password: str) -> bool:
    """El hash de data/ tiene prioridad sobre ARIA_PASSWORD."""
    almacenado = _leer().get("hash")
    if almacenado:
        return verificar_hash(password, almacenado)
    return hmac.compare_digest(password.encode(), config.PASSWORD.encode())


def habilitado() -> bool:
    return bool(config.USER and (config.PASSWORD or _leer().get("hash")) and len(config.SECRET) >= 16)


def credenciales_ok(user: str, password: str) -> bool:
    u = hmac.compare_digest(user.encode(), config.USER.encode())
    p = password_ok(password)
    return habilitado() and u and p


def crear_sesion() -> str:
    return _ser.dumps({"u": config.USER, "v": version_sesion()})


def sesion_valida(token: str | None) -> bool:
    if not token or not habilitado():
        return False
    try:
        datos = _ser.loads(token, max_age=MAX_AGE)
    except BadSignature:
        return False
    if datos.get("v", 1) != version_sesion():
        return False
    return hmac.compare_digest(str(datos.get("u", "")).encode(), config.USER.encode())


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
