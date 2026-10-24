"""Módulo «RUNA»: secretos cifrados de extremo a extremo que se autodestruyen al leerse.

RUNA (https://github.com/BertMarti/runa) corre en su propio contenedor (ver README.md y compose.ejemplo.yml).
ARIA cifra aquí mismo con el protocolo de RUNA (`protocolo.py`) y solo sube ruido cifrado: el servidor de
RUNA nunca ve el texto ni la llave, que viaja en el fragmento «#» del enlace.

- `runa_compartir(texto, caducidad, lecturas)`: «comparte la clave del wifi por RUNA». El texto pasa por el
  chat (y por el modelo); con un cerebro en la nube, mejor `runa_generar` o la web de RUNA.
- `runa_generar(longitud, caducidad, lecturas)`: genera una contraseña aquí y crea dos enlaces (uno para ti y
  otro para compartir). La contraseña nunca llega al modelo ni a la conversación.
- Chequeo «caido»: avisa al administrador si RUNA deja de responder.

Configuración (.env): `RUNA_URL` (dirección interna, p. ej. http://runa:8080) y `RUNA_URL_PUBLICA` (base de los
enlaces que se comparten, con HTTPS; por defecto `RUNA_URL`).
"""
import re
import secrets
import string
from urllib.parse import urlsplit

import httpx

from . import protocolo

TIEMPO_MAX_S = 8
_ID = re.compile(r"^[A-Za-z0-9_-]{22}$")
# Caducidades que acepta RUNA, en segundos, con su nombre.
CADUCIDADES = [(300, "5 minutos"), (3600, "1 hora"), (86_400, "1 día"), (604_800, "7 días")]
_UNIDADES = [(r"seg", 1), (r"min", 60), (r"h(ora)?s?\b", 3600), (r"d[ií]a", 86_400), (r"semana", 604_800),
             (r"mes", 2_592_000), (r"a[ñn]o", 31_536_000)]
_NUMEROS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
            "diez": 10, "quince": 15, "veinte": 20, "treinta": 30, "media": 0.5}
# Sin caracteres que se confunden (0/O, 1/l/I) para poder dictarla o copiarla a mano.
_LETRAS = "abcdefghijkmnopqrstuvwxyz"
_MAYUS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_DIGITOS = "23456789"
_SIMBOLOS = "-_.!@#%+=?"
_SECRETO = (r"\b(contraseñ\w*|clave\w*|secreto\w*|password\w*|pin|credencial\w*|token\w*|wi-?fi)\b")


def leer_caducidad(texto) -> tuple[int, str]:
    """«5 min», «1 hora», «un día», «una semana», «90» (minutos) → la caducidad de RUNA más corta que la cubre."""
    t = str(texto or "").strip().lower()
    if not t:
        return CADUCIDADES[2]
    m = re.search(r"(\d+(?:[.,]\d+)?)", t)
    if m:
        n = float(m.group(1).replace(",", "."))
    else:
        n = next((v for k, v in _NUMEROS.items() if re.search(rf"\b{k}\b", t)), 1)
    factor = next((f for patron, f in _UNIDADES if re.search(patron, t)), 60)   # sin unidad: minutos
    segundos = max(1, n * factor)
    return next((c for c in CADUCIDADES if c[0] >= segundos), CADUCIDADES[-1])


def leer_lecturas(valor) -> int:
    try:
        n = int(float(str(valor).strip()))
    except (TypeError, ValueError):
        return 1
    return max(1, min(10, n))


def generar_contrasena(longitud: int = 20) -> str:
    longitud = max(12, min(64, longitud))
    todos = _LETRAS + _MAYUS + _DIGITOS + _SIMBOLOS
    while True:
        c = "".join(secrets.choice(todos) for _ in range(longitud))
        if all(any(ch in grupo for ch in c) for grupo in (_LETRAS, _MAYUS, _DIGITOS, _SIMBOLOS)):
            return c


def _base(url: str | None, nombre: str) -> str:
    url = (url or "").strip().rstrip("/")
    partes = urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.hostname or partes.username or partes.password:
        raise ValueError(f"{nombre} debe ser una dirección http(s) sin usuario ni contraseña")
    return url


def registrar(aria):
    interna = _base(aria.config("RUNA_URL"), "RUNA_URL")
    publica = _base(aria.config("RUNA_URL_PUBLICA") or interna, "RUNA_URL_PUBLICA")
    if urlsplit(publica).scheme != "https" and urlsplit(publica).hostname not in ("localhost", "127.0.0.1"):
        aria.log.warning("RUNA_URL_PUBLICA no usa HTTPS: los navegadores no podrán descifrar los enlaces")

    async def crear(texto: str, ttl: int, vistas: int) -> str:
        """Cifra aquí, sube solo el cifrado y devuelve el enlace completo."""
        try:
            sellado = protocolo.sellar(texto)
        except protocolo.ProtocoloError as e:
            raise aria.Error(str(e)) from None
        cuerpo = {"ciphertext": sellado["ciphertext"], "verifier": sellado["verifier"],
                  "linkVerifier": sellado["linkVerifier"], "ttl": ttl, "views": vistas}
        try:
            async with httpx.AsyncClient(timeout=TIEMPO_MAX_S, follow_redirects=False) as cli:
                r = await cli.post(f"{interna}/api/secrets", json=cuerpo)
        except httpx.HTTPError:
            raise aria.Error("RUNA no responde. ¿Está en marcha su contenedor?") from None
        if r.status_code == 429:
            raise aria.Error("RUNA está limitando peticiones: prueba de nuevo en un minuto.")
        if r.status_code == 507:
            raise aria.Error("RUNA no tiene espacio para más secretos ahora mismo.")
        if r.status_code != 201:
            raise aria.Error(f"RUNA rechazó el secreto (código {r.status_code}).")
        sid = (r.json() or {}).get("id", "")
        if not isinstance(sid, str) or not _ID.match(sid):
            raise aria.Error("RUNA devolvió una respuesta inesperada.")
        return f"{publica}/s/{sid}#{sellado['fragmento']}"

    def resumen(nombre_ttl: str, vistas: int) -> str:
        return f"caduca en {nombre_ttl}, {vistas} {'lectura' if vistas == 1 else 'lecturas'}"

    @aria.herramienta(
        "runa_compartir",
        "Crea con RUNA un enlace de un solo uso, cifrado de extremo a extremo, para compartir un texto secreto "
        "(contraseña, clave del wifi, código, nota privada). El enlace se autodestruye al leerse o al caducar. "
        "Devuelve el enlace para que el usuario lo envíe. No repitas el texto secreto en tu respuesta.",
        {"texto": ("string", "El secreto exacto que hay que compartir"),
         "caducidad": ("string", "Cuánto dura: 5 min, 1 hora, 1 día (por defecto) o 7 días"),
         "lecturas": ("integer", "Cuántas veces se puede abrir, de 1 (por defecto) a 10")},
        ("texto",),
        roles=("admin", "usuario"), agentes=("aria", "seguridad"),
        intenciones=[
            r"\bruna\b",
            (r"\b(compart\w*|env[ií]\w*|mand\w*|p[aá]sa\w*|enlace)\b", _SECRETO),
        ])
    async def runa_compartir(texto: str, caducidad: str = "", lecturas: int = 1) -> str:
        texto = (texto or "").strip()
        if not texto:
            raise aria.Error("Falta el texto secreto que hay que compartir.")
        ttl, nombre = leer_caducidad(caducidad)
        vistas = leer_lecturas(lecturas)
        enlace = await crear(texto, ttl, vistas)
        return (f"Enlace de RUNA listo ({resumen(nombre, vistas)}):\n{enlace}\n"
                "Quien lo abra verá el secreto y después se borrará. El servidor de RUNA no puede leerlo: "
                "la llave es la parte del enlace que va tras «#», así que hay que copiarlo entero.")

    @aria.herramienta(
        "runa_generar",
        "Genera una contraseña segura nueva y la comparte con RUNA sin que aparezca en la conversación: crea un "
        "enlace para el usuario y otro para la persona que la necesite. Úsala cuando pidan crear o generar una "
        "contraseña o clave para compartirla.",
        {"longitud": ("integer", "Número de caracteres, de 12 a 64 (por defecto 20)"),
         "caducidad": ("string", "Cuánto duran los enlaces: 5 min, 1 hora, 1 día (por defecto) o 7 días"),
         "lecturas": ("integer", "Cuántas veces se puede abrir el enlace para compartir, de 1 (por defecto) a 10")},
        roles=("admin", "usuario"), agentes=("aria", "seguridad"),
        intenciones=[
            (r"\b(gener\w*|cre[ae]\w*|invent\w*|nuev[ao]s?)\b", r"\b(contraseñ\w*|clave\w*|password\w*)\b"),
        ])
    async def runa_generar(longitud: int = 20, caducidad: str = "", lecturas: int = 1) -> str:
        try:
            n = int(float(str(longitud).strip() or 20))
        except ValueError:
            n = 20
        clave = generar_contrasena(n)
        ttl, nombre = leer_caducidad(caducidad)
        vistas = leer_lecturas(lecturas)
        para_ti = await crear(clave, ttl, 1)
        compartir = await crear(clave, ttl, vistas)
        return (f"Contraseña nueva de {max(12, min(64, n))} caracteres creada; no aparece en esta conversación.\n"
                f"Enlace para ti (1 lectura, caduca en {nombre}):\n{para_ti}\n"
                f"Enlace para compartir ({resumen(nombre, vistas)}):\n{compartir}\n"
                "Ambos llevan la misma contraseña y se autodestruyen al leerse.")

    @aria.chequeo("caido", intervalo_min=5, severidad="aviso", confirmaciones=2,
                  texto_ok="RUNA vuelve a responder.")
    async def caido():
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as cli:
                r = await cli.get(f"{interna}/api/health")
            ok = r.status_code == 200
        except httpx.HTTPError:
            ok = False
        return [] if ok else [aria.Problema("runa", "RUNA no responde: no se pueden crear ni abrir secretos.")]
