"""SDK de los módulos de ARIA: lo único que un módulo debería usar del núcleo.

Un módulo (`modulos/<id>/modulo.py`) define `registrar(aria)` y recibe un objeto `Aria` con:

- `aria.herramienta(...)`: decorador que registra una herramienta del chat (con sus intenciones para el
  modelo local, sus roles y los agentes que la ofrecen);
- `aria.chequeo(...)`: decorador que registra una comprobación periódica del motor de avisos (Telegram/push);
- `aria.router(usuario=[...])`: un `APIRouter` ya colgado de `/api/modulos/<id>`; solo para admin salvo las
  rutas que se declaren para `usuario`;
- `aria.config(nombre)`: lee una variable de entorno declarada en el manifiesto (`env` o `env_opcional`);
- `aria.datos()`: carpeta de datos propia (`data/modulos/<id>`);
- `aria.comprobar_url(url)` / `aria.leer_url(url)`: peticiones web con la protección anti-SSRF de `enlaces.py`;
- `aria.log`, `aria.Problema` y `aria.Error`.

Nada se aplica mientras `registrar` se ejecuta: el SDK lo valida y lo apunta, y el cargador (`modulos.py`) lo
registra todo junto solo si `registrar` termina sin errores. Así un módulo roto no deja medio registro.
Esta interfaz es estable (`VERSION_SDK`); lo demás del núcleo puede cambiar sin aviso.
"""
import inspect
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.routing import APIRoute

from . import agentes as _agentes, avisos, config, enlaces, tools
from .avisos import Problema

VERSION_SDK = 1
TIPOS_PARAM = {"string", "integer", "number", "boolean"}
ROLES = ("admin", "usuario")
METODOS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_NOMBRE_HERRAMIENTA = re.compile(r"[a-z][a-z0-9_]{2,47}")
_NOMBRE_PARAM = re.compile(r"[a-z_][a-z0-9_]{0,31}")
_NOMBRE_CHEQUEO = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
_RUTA = re.compile(r"/[A-Za-z0-9_\-./{}]*")
MAX_HERRAMIENTAS = 20
MAX_CHEQUEOS = 5


class ModuloError(Exception):
    """Fallo al cargar o validar un módulo (mensaje en español que se enseña en Ajustes → Módulos)."""


class Error(Exception):
    """Error «legible» de una herramienta de módulo: su texto llega tal cual al modelo (sin traza)."""


tools.registrar_errores(Error)


def _texto(v, campo: str, minimo: int = 1, maximo: int = 500) -> str:
    if not isinstance(v, str) or not (minimo <= len(v.strip()) <= maximo):
        raise ModuloError(f"«{campo}» debe ser un texto de {minimo} a {maximo} caracteres")
    return v.strip()


def _intenciones(lista) -> list:
    """Cada intención es un patrón (basta con que aparezca) o una lista de patrones que deben cumplirse TODOS;
    un patrón que empieza por «!» NO debe aparecer. Mismo formato que `tools._INTENCIONES`."""
    if isinstance(lista, str) or not isinstance(lista, (list, tuple)) or not lista:
        raise ModuloError("cada herramienta necesita al menos una intención (lista de expresiones regulares); "
                          "sin ella el modelo local nunca la recibe")
    if len(lista) > 10:
        raise ModuloError("como mucho 10 intenciones por herramienta")
    out = []
    for i in lista:
        grupo = (i,) if isinstance(i, str) else i
        if not isinstance(grupo, (list, tuple)) or not 1 <= len(grupo) <= 5:
            raise ModuloError("una intención es un patrón o una lista de 1 a 5 patrones")
        for p in grupo:
            if not isinstance(p, str) or not p.strip("!") or len(p) > 300:
                raise ModuloError("cada patrón de intención es un texto de 1 a 300 caracteres")
            try:
                re.compile(p[1:] if p.startswith("!") else p)
            except re.error as e:
                raise ModuloError(f"intención no válida «{p}»: {e}") from None
        if all(p.startswith("!") for p in grupo):
            raise ModuloError("una intención no puede ser solo de patrones negados («!»)")
        out.append(tuple(grupo))
    return out


class Aria:
    """Lo que recibe `registrar(aria)`. Una instancia por módulo."""

    Problema = Problema
    Error = Error
    VERSION_SDK = VERSION_SDK

    def __init__(self, id_: str, env: list | tuple = (), env_opcional: list | tuple = ()):
        self.id = id_
        self.log = logging.getLogger(f"aria.modulos.{id_}")
        self._env = set(env) | set(env_opcional)
        self.prefijo = f"/api/modulos/{id_}"
        # Pendiente de registrar (lo aplica modulos.py si `registrar` termina bien).
        self.herramientas: list = []
        self.chequeos: list = []
        self.routers: list = []   # (APIRouter, [(método, ruta completa)] para usuario)

    # --- Herramientas del chat ---------------------------------------------------------------------------------
    def herramienta(self, nombre: str, descripcion: str, params: dict | None = None, requeridos=(), *,
                    solo_lectura: bool = False, intenciones=(), roles=("admin",), agentes=("aria",)):
        """Decorador para una función `async` que devuelve un texto (o algo serializable a JSON).

        - `params`: {"nombre": ("string"|"integer"|"number"|"boolean", "descripción")}; `requeridos`: obligatorios.
        - `solo_lectura=True`: solo consulta (no cambia nada); entonces también la pueden usar las rutinas.
        - `intenciones`: patrones (regex, en minúsculas) que deben aparecer en el mensaje para ofrecerla al
          modelo local; obligatorio al menos uno.
        - `roles`: quién puede usarla (admin siempre). `agentes`: qué agentes la ofrecen (sin «aria», solo el
          especialista)."""
        if not isinstance(nombre, str) or not _NOMBRE_HERRAMIENTA.fullmatch(nombre):
            raise ModuloError(f"nombre de herramienta no válido: {nombre!r} (minúsculas, números y _, 3-48)")
        if nombre in tools.NUCLEO:
            raise ModuloError(f"la herramienta «{nombre}» choca con una del núcleo de ARIA")
        if any(h["nombre"] == nombre for h in self.herramientas):
            raise ModuloError(f"la herramienta «{nombre}» está repetida")
        if len(self.herramientas) >= MAX_HERRAMIENTAS:
            raise ModuloError(f"como mucho {MAX_HERRAMIENTAS} herramientas por módulo")
        descripcion = _texto(descripcion, "descripcion", 5, 500)
        params = params or {}
        if not isinstance(params, dict) or len(params) > 8:
            raise ModuloError("«params» debe ser un diccionario de 8 parámetros como mucho")
        limpios = {}
        for k, v in params.items():
            if not isinstance(k, str) or not _NOMBRE_PARAM.fullmatch(k) or k == "uid":
                raise ModuloError(f"parámetro no válido: {k!r}")
            if not (isinstance(v, (tuple, list)) and len(v) == 2 and v[0] in TIPOS_PARAM and isinstance(v[1], str)):
                raise ModuloError(f"el parámetro «{k}» debe ser (tipo, descripción) con tipo en {sorted(TIPOS_PARAM)}")
            limpios[k] = (v[0], v[1][:300])
        requeridos = tuple(requeridos)
        if not set(requeridos) <= set(limpios):
            raise ModuloError("«requeridos» incluye parámetros que no están en «params»")
        roles = tuple(roles) if isinstance(roles, (list, tuple)) else ()
        if not roles or not set(roles) <= set(ROLES):
            raise ModuloError(f"«roles» debe ser una lista con {list(ROLES)}")
        agentes = tuple(agentes) if isinstance(agentes, (list, tuple)) else ()
        if not agentes or not set(agentes) <= set(_agentes.AGENTES):
            raise ModuloError(f"«agentes» debe ser una lista con {sorted(_agentes.AGENTES)}")
        entradas = _intenciones(list(intenciones) if isinstance(intenciones, tuple) else intenciones)

        def deco(fn):
            if not inspect.iscoroutinefunction(fn):
                raise ModuloError(f"la herramienta «{nombre}» debe ser una función async")
            self.herramientas.append({"nombre": nombre, "fn": fn, "descripcion": descripcion, "params": limpios,
                                      "requeridos": requeridos, "solo_lectura": bool(solo_lectura),
                                      "usuario": "usuario" in roles, "intenciones": entradas,
                                      "agentes": agentes})
            return fn
        return deco

    # --- Avisos -----------------------------------------------------------------------------------------------
    def chequeo(self, nombre: str, fn=None, *, intervalo_min: int = 5, severidad: str = "aviso",
                confirmaciones: int = 2, cooldown_min: int = 30, texto_ok=None, para_todos: bool = False):
        """Comprobación periódica para el motor de avisos (se usa como decorador o pasando `fn`).

        `fn` es `async` sin argumentos y devuelve una lista de problemas activos (`aria.Problema(clave, texto)` o
        simplemente textos), una lista vacía si todo va bien o None si no puede saberlo. El motor se encarga de
        no repetir, de confirmar (`confirmaciones` pasadas seguidas), del «todo en orden» (`texto_ok`) y de
        entregarlo por Telegram/push. Por defecto solo a los administradores (`para_todos=True`: a todos)."""
        if not isinstance(nombre, str) or not _NOMBRE_CHEQUEO.fullmatch(nombre):
            raise ModuloError(f"nombre de chequeo no válido: {nombre!r}")
        if any(c["nombre"] == nombre for c in self.chequeos):
            raise ModuloError(f"el chequeo «{nombre}» está repetido")
        if len(self.chequeos) >= MAX_CHEQUEOS:
            raise ModuloError(f"como mucho {MAX_CHEQUEOS} chequeos por módulo")
        if severidad not in avisos.SEVERIDADES:
            raise ModuloError(f"«severidad» debe ser una de {list(avisos.SEVERIDADES)}")
        if not (isinstance(intervalo_min, int) and 1 <= intervalo_min <= 1440):
            raise ModuloError("«intervalo_min» debe estar entre 1 y 1440")
        if not (isinstance(confirmaciones, int) and 1 <= confirmaciones <= 10):
            raise ModuloError("«confirmaciones» debe estar entre 1 y 10")
        if not (isinstance(cooldown_min, int) and 0 <= cooldown_min <= 10080):
            raise ModuloError("«cooldown_min» debe estar entre 0 y 10080")
        if texto_ok is not None and not (isinstance(texto_ok, str) or callable(texto_ok)):
            raise ModuloError("«texto_ok» debe ser un texto o una función")

        def deco(f):
            if not inspect.iscoroutinefunction(f):
                raise ModuloError(f"el chequeo «{nombre}» debe ser una función async")
            self.chequeos.append({"nombre": nombre, "fn": f, "intervalo_s": intervalo_min * 60,
                                  "severidad": severidad, "confirmaciones": confirmaciones,
                                  "cooldown_s": cooldown_min * 60, "texto_ok": texto_ok,
                                  "solo_admin": not para_todos})
            return f
        return deco(fn) if fn is not None else deco

    # --- Endpoints -----------------------------------------------------------------------------------------------
    def router(self, usuario=()) -> APIRouter:
        """Devuelve un `APIRouter` colgado de `/api/modulos/<id>` (usa rutas relativas: `@r.get("/estado")`).
        Todas sus rutas son solo de admin salvo las de `usuario`, p. ej. `[("GET", "/estado")]`. Sin WebSocket."""
        lista = []
        for item in usuario or ():
            if not (isinstance(item, (tuple, list)) and len(item) == 2 and isinstance(item[0], str)
                    and isinstance(item[1], str)):
                raise ModuloError("«usuario» es una lista de (método, ruta)")
            metodo, ruta = item[0].upper(), item[1]
            if metodo not in METODOS or not _RUTA.fullmatch(ruta) or ".." in ruta:
                raise ModuloError(f"ruta para usuario no válida: {metodo} {ruta}")
            lista.append((metodo, self.prefijo + ruta))
        r = APIRouter(prefix=self.prefijo)
        self.routers.append((r, lista))
        return r

    # --- Configuración y datos -------------------------------------------------------------------------------
    def config(self, nombre: str, defecto: str | None = None) -> str | None:
        """Valor de una variable de entorno DECLARADA en el manifiesto (`env` o `env_opcional`); vacía = defecto."""
        if nombre not in self._env:
            raise ModuloError(f"la variable «{nombre}» no está declarada en «env» ni en «env_opcional»")
        v = os.environ.get(nombre, "").strip()
        return v or defecto

    def datos(self) -> Path:
        """Carpeta propia para guardar datos (`data/modulos/<id>`), creada si no existe."""
        p = Path(config.DATA_DIR) / "modulos" / self.id
        p.mkdir(parents=True, exist_ok=True)
        return p

    # --- Web con protección anti-SSRF ---------------------------------------------------------------------------
    @staticmethod
    async def comprobar_url(url: str) -> dict:
        """{url, estado, ok, ms} de una web PÚBLICA (nunca la red de casa). Lanza `aria.Error` si no responde."""
        try:
            return await enlaces.comprobar(url)
        except enlaces.EnlaceError as e:
            raise Error(str(e)) from None

    @staticmethod
    async def leer_url(url: str) -> str:
        """Texto legible de una página PÚBLICA, ya preparado para el modelo. Lanza `aria.Error`."""
        try:
            return await enlaces.leer(url)
        except enlaces.EnlaceError as e:
            raise Error(str(e)) from None


def rutas_de(router: APIRouter) -> list:
    """(método, ruta completa) de cada ruta HTTP del router. Lanza ModuloError si hay algo que no sea HTTP."""
    out = []
    for r in router.routes:
        if not isinstance(r, APIRoute):
            raise ModuloError("los módulos solo pueden declarar rutas HTTP (sin WebSocket ni montajes)")
        out += [(m, r.path) for m in sorted(r.methods - {"HEAD", "OPTIONS"})]
    return out
