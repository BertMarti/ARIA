"""Sesion firmada, comparacion en tiempo constante y limitador de intentos."""
import hmac
import time

from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import config

COOKIE = "aria_session"
MAX_AGE = 7 * 24 * 3600
VENTANA = 300      # segundos
MAX_FALLOS = 5

_ser = URLSafeTimedSerializer(config.SECRET or "sin-secreto", salt="aria-session")
_fallos: dict = {}


def habilitado() -> bool:
    return bool(config.USER and config.PASSWORD and len(config.SECRET) >= 16)


def credenciales_ok(user: str, password: str) -> bool:
    u = hmac.compare_digest(user.encode(), config.USER.encode())
    p = hmac.compare_digest(password.encode(), config.PASSWORD.encode())
    return habilitado() and u and p


def crear_sesion() -> str:
    return _ser.dumps({"u": config.USER})


def sesion_valida(token: str | None) -> bool:
    if not token or not habilitado():
        return False
    try:
        datos = _ser.loads(token, max_age=MAX_AGE)
    except BadSignature:
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
