"""Módulo «RUNA»: secretos cifrados de extremo a extremo que se autodestruyen al leerse.

RUNA (https://github.com/BertMarti/runa) corre en su propio contenedor (ver README.md y compose.ejemplo.yml).
ARIA cifra aquí mismo con el protocolo de RUNA (`protocolo.py`) y solo sube ruido cifrado: el servidor de
RUNA nunca ve el texto ni la llave, que viaja en el fragmento «#» del enlace.

- `runa_compartir(texto, caducidad, lecturas)`: «comparte la clave del wifi por RUNA». El texto lo escribe la
  persona en el chat, así que pasa por el modelo y queda en el historial: es para secretos poco sensibles.
- `runa_generar(longitud, caducidad, lecturas)`: genera una contraseña aquí y crea dos secretos en RUNA. Al modelo
  no le llega ni la contraseña ni los enlaces de RUNA (que llevan la llave), sino dos **tickets de ARIA** de un
  solo uso: `GET /api/modulos/runa/recoger/<ticket>` exige sesión en ARIA y entrega el enlace al navegador. Un
  proveedor de IA en la nube que vea el ticket no puede usarlo, y en el historial solo queda un ticket gastado.
- Chequeo «caido»: avisa al administrador si RUNA deja de responder.

Configuración (.env): `RUNA_URL` (dirección interna, p. ej. http://runa:8080) y `RUNA_URL_PUBLICA` (base de los
enlaces que se comparten, con HTTPS; por defecto `RUNA_URL`). Los tickets usan `ARIA_URL_PUBLICA` o, si no hay,
`https://ARIA_LAN_IP`.
"""
import re
import secrets
import time
from urllib.parse import urlsplit

import httpx
from fastapi.responses import PlainTextResponse, RedirectResponse

from . import protocolo

TIEMPO_MAX_S = 8
_ID = re.compile(r"^[A-Za-z0-9_-]{22}$")
_TICKET = re.compile(r"^[A-Za-z0-9_-]{43}$")
TICKET_VIDA_S = 30 * 60
MAX_TICKETS = 200
_SIN_CACHE = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"}
# ticket → {"enlace", "modo": "ver"|"compartir", "detalle", "caduca"}. Solo en memoria: al reiniciar ARIA se pierden.
_tickets: dict[str, dict] = {}
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


def _limpiar_tickets(ahora: float) -> None:
    for t in [t for t, v in _tickets.items() if v["caduca"] <= ahora]:
        del _tickets[t]
    while len(_tickets) >= MAX_TICKETS:                       # los más antiguos primero
        del _tickets[next(iter(_tickets))]


def emitir_ticket(enlace: str, modo: str, detalle: str) -> str:
    ahora = time.time()
    _limpiar_tickets(ahora)
    ticket = secrets.token_urlsafe(32)
    _tickets[ticket] = {"enlace": enlace, "modo": modo, "detalle": detalle, "caduca": ahora + TICKET_VIDA_S}
    return ticket


def registrar(aria):
    interna = _base(aria.config("RUNA_URL"), "RUNA_URL")
    publica = _base(aria.config("RUNA_URL_PUBLICA") or interna, "RUNA_URL_PUBLICA")
    lan = aria.config("ARIA_LAN_IP")
    base_aria = _base(aria.config("ARIA_URL_PUBLICA") or (f"https://{lan}" if lan else "https://localhost"),
                      "ARIA_URL_PUBLICA")
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
        "Crea con RUNA un enlace de un solo uso, cifrado de extremo a extremo, para compartir un texto poco "
        "sensible que el usuario ya ha escrito (p. ej. la clave del wifi de invitados). El enlace se autodestruye "
        "al leerse o al caducar. No repitas el texto secreto en tu respuesta. Si el usuario quiere una contraseña "
        "nueva, usa runa_generar.",
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
                "la llave es la parte del enlace que va tras «#», así que hay que copiarlo entero.\n"
                "Aviso: el texto que escribiste sigue en esta conversación. Para secretos importantes, borra la "
                "conversación o usa la web de RUNA directamente.")

    @aria.herramienta(
        "runa_generar",
        "Genera una contraseña segura nueva y la comparte con RUNA sin que la contraseña ni sus enlaces pasen por "
        "la conversación: devuelve dos enlaces de ARIA de un solo uso (uno para verla y otro para obtener el "
        "enlace que se comparte) que solo funcionan con la sesión del usuario. Úsala cuando pidan crear o generar "
        "una contraseña o clave, para sí o para compartirla. Copia los enlaces de ARIA tal cual.",
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
        ver = emitir_ticket(await crear(clave, ttl, 1), "ver", f"1 lectura, caduca en {nombre}")
        compartir = emitir_ticket(await crear(clave, ttl, vistas), "compartir", resumen(nombre, vistas))
        recoger = f"{base_aria}{aria.prefijo}/recoger"
        return (f"Contraseña nueva de {max(12, min(64, n))} caracteres creada. Ni la contraseña ni los enlaces de "
                "RUNA aparecen aquí: estos dos enlaces de ARIA solo funcionan con tu sesión iniciada, una sola vez y "
                "durante 30 minutos.\n"
                f"Para ver tú la contraseña: {recoger}/{ver}\n"
                f"Para obtener el enlace que envías ({resumen(nombre, vistas)}): {recoger}/{compartir}")

    r = aria.router(usuario=[("GET", "/recoger/{ticket}")])

    @r.get("/recoger/{ticket}")
    async def recoger(ticket: str):
        """Entrega al navegador (con sesión en ARIA) el enlace de RUNA de un ticket. Un solo uso."""
        datos = _tickets.pop(ticket, None) if _TICKET.match(ticket) else None
        if not datos or datos["caduca"] <= time.time():
            return PlainTextResponse("Este enlace de ARIA ya se usó o caducó. Pide otra contraseña a ARIA.\n",
                                     status_code=404, headers=_SIN_CACHE)
        if datos["modo"] == "ver":
            # El fragmento «#» con la llave va en Location: lo recibe solo este navegador.
            return RedirectResponse(datos["enlace"], status_code=303, headers=_SIN_CACHE)
        return PlainTextResponse(
            "Enlace de RUNA para compartir. Cópialo entero (incluida la parte tras #) y envíalo:\n\n"
            f"{datos['enlace']}\n\n{datos['detalle'].capitalize()}. Se autodestruye al leerse.\n"
            "Esta página de ARIA ya no se puede volver a abrir.\n", headers=_SIN_CACHE)

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
