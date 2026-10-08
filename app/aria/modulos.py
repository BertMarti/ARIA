"""Módulos: aplicaciones y funciones que cualquiera puede enchufar a ARIA sin tocar el núcleo.

Cada módulo vive en `modulos/<id>/` (en el contenedor, `/srv/modulos`, montado de solo lectura) con:
- `modulo.json`: manifiesto (nombre, versión, icono, enlace para el lanzador de Inicio, chequeo de salud,
  variables de entorno que necesita y roles que lo ven);
- `modulo.py` (opcional): `registrar(aria)` con el SDK de `sdk.py` (herramientas del chat, chequeos de avisos,
  endpoints bajo `/api/modulos/<id>/`).

Reglas del cargador:
- se ignoran las carpetas que empiezan por «_» o «.» (p. ej. `_plantilla`);
- `ARIA_MODULOS`: lista separada por comas de los que se activan; vacía o «*» = todos; «-» = ninguno;
- el manifiesto se valida de forma estricta (claves desconocidas = error, salvo las que empiezan por «_»,
  que sirven de comentario);
- si falta una variable de `env`, el módulo queda «sin configurar» y su código NO se ejecuta;
- un módulo roto NUNCA tumba ARIA: se captura el error, se registra en el log y el módulo queda en «error»
  con su mensaje. Lo que hubiera registrado a medias se deshace.

Los módulos son código Python de confianza (como cualquier plugin): se ejecutan dentro de la app con sus
permisos. Instala solo módulos que hayas leído o de alguien de quien te fíes.
"""
import asyncio
import importlib.util
import inspect
import json
import logging
import os
import re
import sys
import time
import types
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from . import avisos, config, permisos, services, shield, tools, vpn
from .avisos import Chequeo, Problema
from .sdk import Aria, ModuloError, rutas_de

log = logging.getLogger("aria.modulos")

ID_RE = re.compile(r"[a-z0-9-]{2,32}")
ENV_RE = re.compile(r"[A-Z][A-Z0-9_]{1,63}")
HOST_RE = re.compile(r"[A-Za-z0-9.\-]{1,253}")
ICONOS = ("app", "web", "escudo", "candado", "servidor", "grafica", "casa", "musica", "nube", "reloj",
          "herramienta", "red", "camara", "documento")
CLAVES = {"id", "nombre", "descripcion", "version", "icono", "url", "salud", "env", "env_opcional", "roles"}
MAX_MANIFIESTO = 64 * 1024
SALUD_CACHE_S = 20
SALUD_TIMEOUT_S = 3.0


@dataclass
class Modulo:
    id: str
    carpeta: str
    manifiesto: dict = field(default_factory=dict)
    estado: str = "activo"          # activo | sin_configurar | desactivado | error
    error: str = ""
    integrado: bool = False
    herramientas: list = field(default_factory=list)
    chequeos: list = field(default_factory=list)
    rutas: list = field(default_factory=list)            # (método, ruta)
    rutas_usuario: list = field(default_factory=list)
    _deshacer: list = field(default_factory=list, repr=False)

    def retirar(self) -> None:
        """Deshace todo lo registrado (en orden inverso). No lanza."""
        while self._deshacer:
            fn = self._deshacer.pop()
            try:
                fn()
            except Exception:  # noqa: BLE001
                log.exception("No se pudo retirar parte del módulo %s", self.id)
        self.herramientas, self.chequeos, self.rutas, self.rutas_usuario = [], [], [], []


_CARGADOS: dict = {}       # id -> Modulo (los de la carpeta modulos/)
_salud_cache: dict = {}    # id -> (instante, estado)


def directorio_defecto() -> Path:
    """`ARIA_MODULOS_DIR`, o `/srv/modulos` en el contenedor, o `<repo>/modulos` al trabajar sin Docker."""
    if os.environ.get("ARIA_MODULOS_DIR"):
        return Path(os.environ["ARIA_MODULOS_DIR"])
    base = Path(__file__).resolve().parent.parent
    for c in (base / "modulos", base.parent / "modulos"):
        if c.is_dir():
            return c
    return base / "modulos"


def habilitados_env(valor: str | None = None) -> set | None:
    """None = todos. Conjunto vacío = ninguno."""
    v = (os.environ.get("ARIA_MODULOS", "") if valor is None else valor).strip()
    if v in ("", "*"):
        return None
    if v in ("-", "ninguno"):
        return set()
    return {x.strip() for x in v.split(",") if x.strip()}


# --- Manifiesto ---------------------------------------------------------------------------------------------
def _lista_env(v, campo: str) -> list:
    if v is None:
        return []
    if not isinstance(v, list) or len(v) > 20 or not all(isinstance(x, str) and ENV_RE.fullmatch(x) for x in v):
        raise ModuloError(f"«{campo}» debe ser una lista de nombres de variable en MAYÚSCULAS (máx. 20)")
    return list(dict.fromkeys(v))


def validar_url_lanzador(url) -> str:
    """URL del lanzador: http(s) con host o «{host}» (= el nombre con el que se entra en ARIA)."""
    if not isinstance(url, str) or not 8 <= len(url) <= 300 or any(c.isspace() for c in url):
        raise ModuloError("«url» debe ser una dirección http:// o https:// de 300 caracteres como mucho")
    prueba = url.replace("{host}", "aria.example")
    try:
        p = urlsplit(prueba)
        p.port
    except ValueError:
        raise ModuloError("«url» no es válida") from None
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or "{" in prueba:
        raise ModuloError("«url» debe empezar por http:// o https://, tener servidor y no llevar usuario ni contraseña")
    return url


def _salud(v) -> dict | None:
    if v is None:
        return None
    if not isinstance(v, dict) or set(v) - {"tipo", "host", "puerto", "ruta", "tls"}:
        raise ModuloError("«salud» admite solo tipo, host, puerto, ruta y tls")
    tipo = v.get("tipo")
    if tipo not in ("http", "tcp", "dns"):
        raise ModuloError("«salud.tipo» debe ser http, tcp o dns")
    host = v.get("host")
    if not isinstance(host, str) or not HOST_RE.fullmatch(host):
        raise ModuloError("«salud.host» no es válido (nombre o IP)")
    puerto = v.get("puerto", {"http": 80, "tcp": None, "dns": 53}[tipo])
    if not isinstance(puerto, int) or isinstance(puerto, bool) or not 1 <= puerto <= 65535:
        raise ModuloError("«salud.puerto» debe ser un número entre 1 y 65535")
    ruta = v.get("ruta", "/")
    if not isinstance(ruta, str) or not ruta.startswith("/") or len(ruta) > 200 or any(c.isspace() for c in ruta):
        raise ModuloError("«salud.ruta» debe empezar por «/»")
    tls = v.get("tls", False)
    if not isinstance(tls, bool):
        raise ModuloError("«salud.tls» debe ser true o false")
    return {"tipo": tipo, "host": host, "puerto": puerto, "ruta": ruta, "tls": tls}


def validar_manifiesto(d, carpeta: str) -> dict:
    """Devuelve el manifiesto normalizado o lanza ModuloError con un mensaje en español."""
    if not isinstance(d, dict):
        raise ModuloError("modulo.json debe ser un objeto JSON")
    desconocidas = {k for k in d if not k.startswith("_")} - CLAVES
    if desconocidas:
        raise ModuloError(f"claves desconocidas en modulo.json: {', '.join(sorted(desconocidas))}")
    mid = d.get("id")
    if not isinstance(mid, str) or not ID_RE.fullmatch(mid):
        raise ModuloError("«id» debe tener de 2 a 32 caracteres: minúsculas, números y guiones")
    if mid != carpeta:
        raise ModuloError(f"«id» ({mid}) debe coincidir con el nombre de la carpeta ({carpeta})")
    nombre = d.get("nombre")
    if not isinstance(nombre, str) or not 1 <= len(nombre.strip()) <= 40:
        raise ModuloError("«nombre» es obligatorio (1-40 caracteres)")
    version = d.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z.+-]{1,20}", version):
        raise ModuloError("«version» es obligatoria (p. ej. \"1.0.0\")")
    desc = d.get("descripcion", "")
    if not isinstance(desc, str) or len(desc) > 300:
        raise ModuloError("«descripcion» debe ser un texto de 300 caracteres como mucho")
    icono = d.get("icono", "app")
    if icono not in ICONOS:
        raise ModuloError(f"«icono» debe ser uno de: {', '.join(ICONOS)}")
    roles = d.get("roles", ["admin"])
    if not isinstance(roles, list) or not roles or not set(roles) <= {"admin", "usuario"}:
        raise ModuloError("«roles» debe ser una lista con «admin» y/o «usuario»")
    env = _lista_env(d.get("env"), "env")
    env_op = [e for e in _lista_env(d.get("env_opcional"), "env_opcional") if e not in env]
    return {"id": mid, "nombre": nombre.strip(), "descripcion": desc.strip(), "version": version, "icono": icono,
            "url": validar_url_lanzador(d["url"]) if d.get("url") is not None else None,
            "salud": _salud(d.get("salud")), "env": env, "env_opcional": env_op,
            "roles": sorted(set(roles) | {"admin"})}


def leer_manifiesto(carpeta: Path) -> dict:
    f = carpeta / "modulo.json"
    if not f.is_file():
        raise ModuloError("falta modulo.json")
    if f.stat().st_size > MAX_MANIFIESTO:
        raise ModuloError("modulo.json es demasiado grande")
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ModuloError(f"modulo.json no es JSON válido: {e}") from None
    return validar_manifiesto(d, carpeta.name)


def faltan(m: dict) -> list:
    return [e for e in m["env"] if not os.environ.get(e, "").strip()]


# --- Código del módulo --------------------------------------------------------------------------------------
def _importar(mod: Modulo, carpeta: Path):
    """Importa `modulo.py` como `aria_modulos.<id>.modulo` (así puede hacer `from . import otro`)."""
    paquete = "aria_modulos." + mod.id.replace("-", "_")
    if "aria_modulos" not in sys.modules:
        raiz = types.ModuleType("aria_modulos")
        raiz.__path__ = []
        sys.modules["aria_modulos"] = raiz
    for n in [n for n in sys.modules if n == paquete or n.startswith(paquete + ".")]:
        del sys.modules[n]   # recarga limpia (pruebas)
    pkg = types.ModuleType(paquete)
    pkg.__path__ = [str(carpeta)]
    sys.modules[paquete] = pkg
    mod._deshacer.append(lambda: [sys.modules.pop(n, None) for n in list(sys.modules)
                                  if n == paquete or n.startswith(paquete + ".")])
    spec = importlib.util.spec_from_file_location(paquete + ".modulo", carpeta / "modulo.py")
    codigo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = codigo
    spec.loader.exec_module(codigo)
    return codigo


def _envolver_chequeo(mid: str, fn):
    async def chequeo():
        res = await fn()
        if res is None:
            return None
        if not isinstance(res, (list, tuple)):
            raise TypeError("un chequeo debe devolver una lista o None")
        out = []
        for p in res[:50]:
            if isinstance(p, str):
                p = Problema(p[:80], p)
            if not isinstance(p, Problema):
                raise TypeError("un chequeo devuelve Problema o textos")
            out.append(Problema(str(p.clave)[:120], str(p.texto)[:avisos.MAX_TEXTO], p.severidad
                                if p.severidad in avisos.SEVERIDADES else None))
        return out
    return chequeo


def _aplicar(mod: Modulo, sdk: Aria, app) -> None:
    """Registra lo que el SDK apuntó. Si algo falla, el llamador hace `mod.retirar()`."""
    # Validaciones previas (nada se registra si falla alguna)
    for h in sdk.herramientas:
        if h["nombre"] in tools._REGISTRO:
            raise ModuloError(f"la herramienta «{h['nombre']}» ya la registró otro módulo")
    rutas, rutas_usuario = [], []
    for r, usuario in sdk.routers:
        propias = rutas_de(r)
        if not propias:
            continue
        rutas += propias
        for metodo, ruta in usuario:
            if (metodo, ruta) not in propias:
                raise ModuloError(f"la ruta para usuario {metodo} {ruta} no existe en el router")
            rutas_usuario.append((metodo, ruta))
    if len(set(rutas)) != len(rutas):
        raise ModuloError("hay rutas repetidas")
    # Herramientas
    for h in sdk.herramientas:
        tools.registrar_externa(h["nombre"], h["fn"], h["descripcion"], h["params"], h["requeridos"],
                                modulo=mod.id, solo_lectura=h["solo_lectura"], usuario=h["usuario"],
                                intenciones=h["intenciones"], agentes=h["agentes"])
        mod._deshacer.append(lambda n=h["nombre"]: tools.retirar_externa(n))
        mod.herramientas.append({"nombre": h["nombre"], "descripcion": h["descripcion"],
                                 "solo_lectura": h["solo_lectura"], "usuario": h["usuario"]})
    # Chequeos de avisos: un tipo de aviso por módulo (se puede apagar en Ajustes → Avisos)
    if sdk.chequeos:
        tipo = "modulo_" + mod.id.replace("-", "_")
        solo_admin = all(c["solo_admin"] for c in sdk.chequeos)
        avisos.TIPOS[tipo] = (f"Módulo {mod.manifiesto['nombre']}", solo_admin, True)
        mod._deshacer.append(lambda t=tipo: avisos.TIPOS.pop(t, None))
        for c in sdk.chequeos:
            cid = f"modulo:{mod.id}:{c['nombre']}"
            if cid in avisos.chequeos():
                raise ModuloError(f"el chequeo {cid} ya existe")
            avisos.registrar_chequeo(Chequeo(
                cid, tipo, c["severidad"], _envolver_chequeo(mod.id, c["fn"]), intervalo_s=c["intervalo_s"],
                cooldown_s=c["cooldown_s"], confirmaciones=c["confirmaciones"], texto_ok=c["texto_ok"],
                solo_admin=c["solo_admin"]))
            mod._deshacer.append(lambda i=cid: avisos._CHEQUEOS.pop(i, None))
            mod.chequeos.append(c["nombre"])
    # Endpoints (al final: es lo único que toca la app)
    prefijo = sdk.prefijo + "/"
    for metodo, ruta in rutas_usuario:
        permisos.permitir_modulo(metodo, ruta)
    if rutas_usuario:
        mod._deshacer.append(lambda: permisos.retirar_modulo(prefijo))
    for r, _ in sdk.routers:
        if r.routes:
            app.include_router(r)
            mod._deshacer.append(lambda r=r: _quitar_router(app, r, prefijo))
    mod.rutas, mod.rutas_usuario = rutas, rutas_usuario


def _quitar_router(app, router, prefijo: str) -> None:
    app.router.routes[:] = [x for x in app.router.routes
                            if getattr(x, "original_router", None) is not router
                            and not (getattr(x, "path", "") or "").startswith(prefijo)]


def cargar_uno(carpeta: Path, app, habilitados: set | None = None) -> Modulo:
    """Carga un módulo. Nunca lanza: los fallos quedan en `estado="error"` y `error`."""
    mod = Modulo(id=carpeta.name, carpeta=carpeta.name)
    try:
        mod.manifiesto = leer_manifiesto(carpeta)
    except ModuloError as e:
        mod.estado, mod.error = "error", str(e)
        log.error("Módulo %s: %s", carpeta.name, e)
        return mod
    except Exception as e:  # noqa: BLE001
        mod.estado, mod.error = "error", f"No se pudo leer modulo.json ({type(e).__name__})"
        log.exception("Módulo %s: no se pudo leer el manifiesto", carpeta.name)
        return mod
    m = mod.manifiesto
    if habilitados is not None and mod.id not in habilitados:
        mod.estado = "desactivado"
        return mod
    if faltan(m):
        mod.estado = "sin_configurar"
        log.info("Módulo %s sin configurar (faltan: %s)", mod.id, ", ".join(faltan(m)))
        return mod
    if not (carpeta / "modulo.py").is_file():
        return mod   # solo manifiesto: un lanzador con salud
    sdk = Aria(mod.id, m["env"], m["env_opcional"])
    try:
        codigo = _importar(mod, carpeta)
        registrar = getattr(codigo, "registrar", None)
        if registrar is None:
            raise ModuloError("modulo.py no define registrar(aria)")
        if not callable(registrar) or inspect.iscoroutinefunction(registrar):
            raise ModuloError("registrar(aria) debe ser una función normal (no async)")
        registrar(sdk)
        _aplicar(mod, sdk, app)
    except (Exception, SystemExit) as e:  # noqa: BLE001 - un módulo roto nunca tumba ARIA
        mod.retirar()
        mod.estado = "error"
        mod.error = str(e)[:300] if isinstance(e, ModuloError) else f"{type(e).__name__}: {str(e)[:250]}"
        log.exception("El módulo %s falló al cargar", mod.id)
        return mod
    log.info("Módulo %s %s cargado (%d herramientas, %d chequeos, %d rutas)", mod.id, m["version"],
             len(mod.herramientas), len(mod.chequeos), len(mod.rutas))
    return mod


def cargar(app, directorio: Path | None = None, habilitados: set | None | str = "env") -> dict:
    """Descubre y carga los módulos. Devuelve {id: Modulo} y lo deja en `_CARGADOS`. Nunca lanza."""
    try:
        directorio = Path(directorio) if directorio is not None else directorio_defecto()
        if habilitados == "env":
            habilitados = habilitados_env()
        out: dict = {}
        if not directorio.is_dir():
            log.info("Sin carpeta de módulos (%s)", directorio)
        else:
            for carpeta in sorted(directorio.iterdir()):
                if carpeta.name.startswith(("_", ".")) or not carpeta.is_dir():
                    continue
                if carpeta.name in INTEGRADOS:
                    out[carpeta.name] = Modulo(id=carpeta.name, carpeta=carpeta.name, estado="error",
                                               error="ese id es el de una aplicación integrada")
                    continue
                out[carpeta.name] = cargar_uno(carpeta, app, habilitados)
        if habilitados:
            for falta in sorted(habilitados - set(out)):
                log.warning("ARIA_MODULOS pide «%s», pero no existe esa carpeta", falta)
    except Exception:  # noqa: BLE001
        log.exception("Fallo inesperado al cargar los módulos")
        out = {}
    _CARGADOS.clear()
    _CARGADOS.update(out)
    _salud_cache.clear()
    return out


def retirar_todos() -> None:
    for m in _CARGADOS.values():
        m.retirar()
    _CARGADOS.clear()


# --- Aplicaciones integradas (solo informativo: su código sigue en el núcleo) --------------------------------
INTEGRADOS = {
    "shield-dns": {
        "id": "shield-dns", "nombre": "SHIELD-DNS", "version": config.VERSION, "icono": "escudo",
        "descripcion": "Bloqueador de anuncios y DNS de la casa (Pi-hole v6). Repositorio aparte; ARIA lo consulta y lo pausa.",
        "env": ["SHIELD_PASSWORD"], "env_opcional": ["SHIELD_URL", "SHIELD_DNS_HOST", "SHIELD_DNS_PORT", "SHIELD_WEB_PORT"],
        "herramientas": ["estado_servicios", "estado_bloqueador", "pausar_bloqueador", "reanudar_bloqueador",
                         "bloqueos_por_cliente"],
        "roles": ["admin", "usuario"],
    },
    "heimdall": {
        "id": "heimdall", "nombre": "HEIMDALL", "version": config.VERSION, "icono": "candado",
        "descripcion": "VPN WireGuard para entrar en casa desde fuera (wg-easy). Repositorio aparte; ARIA lista y gestiona dispositivos.",
        "env": ["VPN_USER", "VPN_PASSWORD"], "env_opcional": ["VPN_URL", "HEIMDALL_HOST", "HEIMDALL_PORT"],
        "herramientas": ["dispositivos_vpn", "crear_dispositivo_vpn", "activar_dispositivo_vpn",
                         "desactivar_dispositivo_vpn"],
        "roles": ["admin", "usuario"],
    },
}


async def _salud_integrados() -> dict:
    try:
        e = await services.estado()
    except Exception:  # noqa: BLE001
        return {}
    conv = {"ok": "ok", "parcial": "aviso", "no_instalado": "mal"}
    return {"shield-dns": conv.get(e["shield_dns"]["estado"]), "heimdall": conv.get(e["heimdall"]["estado"])}


# --- Salud de los módulos -----------------------------------------------------------------------------------
async def _http_ok(s: dict) -> bool:
    esquema = "https" if s["tls"] else "http"
    host = f"[{s['host']}]" if ":" in s["host"] else s["host"]
    try:
        async with httpx.AsyncClient(timeout=SALUD_TIMEOUT_S, verify=False, follow_redirects=False,
                                     trust_env=False) as c:
            r = await c.get(f"{esquema}://{host}:{s['puerto']}{s['ruta']}")
        return r.status_code < 500
    except httpx.HTTPError:
        return False


async def comprobar_salud(s: dict | None) -> str | None:
    """'ok' | 'mal' | None (sin chequeo)."""
    if not s:
        return None
    if s["tipo"] == "http":
        ok = await _http_ok(s)
    elif s["tipo"] == "tcp":
        ok = await asyncio.to_thread(services._tcp_ok, s["host"], s["puerto"], SALUD_TIMEOUT_S)
    else:
        ok = await asyncio.to_thread(services._dns_ok, s["host"], s["puerto"], "example.com", SALUD_TIMEOUT_S)
    return "ok" if ok else "mal"


async def _salud_de(m: Modulo) -> str | None:
    if m.estado != "activo" or not m.manifiesto.get("salud"):
        return None
    t, v = _salud_cache.get(m.id, (0.0, None))
    if time.monotonic() - t < SALUD_CACHE_S:
        return v
    try:
        v = await asyncio.wait_for(comprobar_salud(m.manifiesto["salud"]), SALUD_TIMEOUT_S + 2)
    except Exception:  # noqa: BLE001
        v = "mal"
    _salud_cache[m.id] = (time.monotonic(), v)
    return v


# --- Lista para la API --------------------------------------------------------------------------------------
def _env_info(nombres: list) -> list:
    # Solo el NOMBRE y si está definida; nunca el valor.
    return [{"nombre": n, "definida": bool(os.environ.get(n, "").strip())} for n in nombres]


async def listar(rol: str) -> list:
    """Integrados + módulos. `usuario` solo ve los suyos activos y sin detalles internos."""
    mods = list(_CARGADOS.values())
    saludes = await asyncio.gather(*(_salud_de(m) for m in mods))
    out = []
    if rol == "admin":
        sal_int = await _salud_integrados()
        conf = {"shield-dns": shield.configurado(), "heimdall": vpn.configurado()}
        for i in INTEGRADOS.values():
            out.append({"id": i["id"], "nombre": i["nombre"], "descripcion": i["descripcion"], "version": i["version"],
                        "icono": i["icono"], "integrado": True, "url": None,
                        "estado": "activo" if conf[i["id"]] else "sin_configurar", "error": "",
                        "salud": sal_int.get(i["id"]),
                        "herramientas": [{"nombre": n} for n in i["herramientas"] if n in tools._REGISTRO],
                        "chequeos": [], "rutas": [], "roles": i["roles"],
                        "env": _env_info(i["env"]), "env_opcional": _env_info(i["env_opcional"])})
    for m, salud in zip(mods, saludes):
        man = m.manifiesto
        if rol != "admin":
            if m.estado != "activo" or "usuario" not in man.get("roles", []):
                continue
            out.append({"id": m.id, "nombre": man["nombre"], "descripcion": man["descripcion"],
                        "icono": man["icono"], "url": man["url"], "estado": m.estado, "salud": salud})
            continue
        out.append({"id": m.id, "nombre": man.get("nombre", m.id), "descripcion": man.get("descripcion", ""),
                    "version": man.get("version", ""), "icono": man.get("icono", "app"), "integrado": False,
                    "url": man.get("url"), "estado": m.estado, "error": m.error, "salud": salud,
                    "herramientas": m.herramientas, "chequeos": m.chequeos,
                    "rutas": [f"{a} {b}" + (" (usuario)" if (a, b) in m.rutas_usuario else "") for a, b in m.rutas],
                    "roles": man.get("roles", ["admin"]),
                    "env": _env_info(man.get("env", [])), "env_opcional": _env_info(man.get("env_opcional", []))})
    return out
