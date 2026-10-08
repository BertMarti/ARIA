"""Módulos enchufables: manifiesto, cargador (aislamiento de fallos), SDK, permisos de sus endpoints, avisos,
salud, API, plantilla y el módulo de ejemplo «uptime». Sin red: DNS y HTTP falsos, sockets solo en 127.0.0.1."""
import asyncio
import http.server
import json
import shutil
import socket
import threading
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aria import agentes, auth, avisos, enlaces, main, modulos, permisos, sdk, tools, usuarios
from aria.sdk import ModuloError

LAN = "https://192.168.1.50"
REPO_MODULOS = Path(__file__).resolve().parents[2] / "modulos"


def correr(c):
    return asyncio.run(c)


def cliente_de(u, app=None) -> TestClient:
    c = TestClient(app or main.app, base_url=LAN, follow_redirects=False)
    if u:
        c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def manifiesto(mid: str, **extra) -> dict:
    return {"id": mid, "nombre": mid.capitalize(), "version": "1.0.0", **extra}


def escribir(base: Path, mid: str, man: dict | str | None = None, codigo: str | None = None) -> Path:
    d = base / mid
    d.mkdir(parents=True, exist_ok=True)
    if man is not None:
        (d / "modulo.json").write_text(man if isinstance(man, str) else json.dumps(man), encoding="utf-8")
    if codigo is not None:
        (d / "modulo.py").write_text(codigo, encoding="utf-8")
    return d


@pytest.fixture
def cargador(tmp_path):
    """Carga módulos de una carpeta temporal en una app nueva y lo deshace todo al acabar (deja los de main)."""
    antes = dict(modulos._CARGADOS)
    base = tmp_path / "mods"
    base.mkdir()
    cargados = []

    def cargar(habilitados=None, app=None, directorio=None):
        app = app or FastAPI()
        res = modulos.cargar(app, directorio or base, habilitados)
        cargados.append(res)
        return res, app
    cargar.base = base
    yield cargar
    for res in cargados:
        for m in res.values():
            m.retirar()
    modulos._CARGADOS.clear()
    modulos._CARGADOS.update(antes)


HERRAMIENTA = '''
def registrar(aria):
    @aria.herramienta("{nombre}", "Herramienta de prueba.", {{"x": ("string", "algo")}}, solo_lectura={lectura},
                      roles={roles}, intenciones=[r"\\b{nombre}\\b"])
    async def h(x: str = "") -> str:
        return "hecho " + x
'''


def herramienta(nombre: str, lectura=True, roles=("admin",)) -> str:
    return HERRAMIENTA.format(nombre=nombre, lectura=lectura, roles=roles)


# --- Los módulos de prueba que carga main.py (conftest: ARIA_MODULOS_DIR=tests/modulos_prueba) ---------------------
def test_main_carga_el_bueno_y_aisla_el_roto():
    demo, roto = modulos._CARGADOS["demo"], modulos._CARGADOS["roto"]
    assert demo.estado == "activo" and not demo.error
    assert {h["nombre"] for h in demo.herramientas} == {"demo_eco", "demo_admin"}
    assert roto.estado == "error" and "explota a propósito" in roto.error
    assert "_ignorado" not in modulos._CARGADOS
    # Lo que el roto llegó a registrar se deshizo: ni herramienta ni intenciones ni ruta.
    assert "roto_herramienta" not in tools._REGISTRO
    assert not any("roto_herramienta" in n for _, n in tools._INTENCIONES)
    assert all("/api/modulos/roto" not in getattr(r, "path", "") for r in _rutas(main.app))


def _rutas(app) -> list:
    out = []
    for r in app.routes:
        out.append(r)
        if hasattr(r, "original_router"):
            out += list(r.original_router.routes)
    return out


# --- Manifiesto -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cambio,trozo", [
    ({"id": "A_B"}, "«id»"), ({"id": "x"}, "«id»"), ({"id": "otro"}, "coincidir"),
    ({"nombre": ""}, "«nombre»"), ({"version": None}, "«version»"), ({"desconocida": 1}, "claves desconocidas"),
    ({"icono": "cohete"}, "«icono»"), ({"url": "javascript:alert(1)"}, "«url»"), ({"url": "ftp://x/"}, "«url»"),
    ({"url": "https://u:p@x.es/"}, "«url»"), ({"url": "https://{otra}/"}, "«url»"),
    ({"salud": {"tipo": "icmp", "host": "x"}}, "salud.tipo"), ({"salud": {"tipo": "tcp", "host": "x"}}, "puerto"),
    ({"salud": {"tipo": "http", "host": "a b"}}, "salud.host"), ({"salud": {"tipo": "http", "host": "x", "extra": 1}}, "salud"),
    ({"salud": {"tipo": "http", "host": "x", "ruta": "sin-barra"}}, "salud.ruta"),
    ({"env": ["minusculas"]}, "«env»"), ({"env": "TOKEN"}, "«env»"), ({"roles": ["root"]}, "«roles»"),
    ({"roles": []}, "«roles»"), ({"descripcion": "x" * 301}, "descripcion"),
])
def test_manifiesto_invalido(cambio, trozo):
    with pytest.raises(ModuloError, match=trozo):
        modulos.validar_manifiesto({**manifiesto("prueba"), **cambio}, "prueba")


def test_manifiesto_valido_y_por_defecto():
    m = modulos.validar_manifiesto({**manifiesto("mi-app"), "_comentario": "se ignora",
                                    "url": "http://{host}:8099/", "env": ["MI_TOKEN", "MI_TOKEN"],
                                    "env_opcional": ["MI_TOKEN", "MI_OTRA"],
                                    "salud": {"tipo": "tcp", "host": "host.docker.internal", "puerto": 8099}}, "mi-app")
    assert m["roles"] == ["admin"] and m["icono"] == "app" and m["env"] == ["MI_TOKEN"]
    assert m["env_opcional"] == ["MI_OTRA"]
    assert m["salud"] == {"tipo": "tcp", "host": "host.docker.internal", "puerto": 8099, "ruta": "/", "tls": False}
    assert modulos.validar_manifiesto({**manifiesto("ab"), "roles": ["usuario"]}, "ab")["roles"] == ["admin", "usuario"]


# --- Cargador --------------------------------------------------------------------------------------------------
def test_habilitados_por_env(monkeypatch):
    assert modulos.habilitados_env("") is None and modulos.habilitados_env("*") is None
    assert modulos.habilitados_env("-") == set()
    assert modulos.habilitados_env(" a, b ,") == {"a", "b"}
    monkeypatch.setenv("ARIA_MODULOS", "uno")
    assert modulos.habilitados_env() == {"uno"}


def test_descubre_ignora_y_desactiva(cargador):
    b = cargador.base
    escribir(b, "uno", manifiesto("uno"), herramienta("mod_uno"))
    escribir(b, "dos", manifiesto("dos"), "raise RuntimeError('no debería ejecutarse')\n")
    escribir(b, "_plantilla", manifiesto("plantilla"), "raise RuntimeError('ignorada')\n")
    escribir(b, ".oculto", manifiesto("oculto"))
    (b / "suelto.txt").write_text("x")
    res, _ = cargador(habilitados={"uno"})
    assert set(res) == {"uno", "dos"}
    assert res["uno"].estado == "activo" and "mod_uno" in tools._REGISTRO
    assert res["dos"].estado == "desactivado" and not res["dos"].error
    res, _ = cargador(habilitados=set())
    assert res["uno"].estado == "desactivado"


def test_cargar_con_ARIA_MODULOS(cargador, monkeypatch):
    escribir(cargador.base, "uno", manifiesto("uno"), herramienta("mod_uno"))
    escribir(cargador.base, "dos", manifiesto("dos"), herramienta("mod_dos"))
    monkeypatch.setenv("ARIA_MODULOS", "dos,no-existe")
    res = modulos.cargar(FastAPI(), cargador.base)
    try:
        assert res["uno"].estado == "desactivado" and res["dos"].estado == "activo"
    finally:
        for m in res.values():
            m.retirar()


def test_sin_configurar_no_ejecuta_el_codigo(cargador, monkeypatch):
    monkeypatch.delenv("MOD_TOKEN", raising=False)
    escribir(cargador.base, "conf", manifiesto("conf", env=["MOD_TOKEN"]), herramienta("mod_conf"))
    res, _ = cargador()
    assert res["conf"].estado == "sin_configurar" and "mod_conf" not in tools._REGISTRO
    res["conf"].retirar()
    monkeypatch.setenv("MOD_TOKEN", "x")
    res, _ = cargador()
    assert res["conf"].estado == "activo" and "mod_conf" in tools._REGISTRO


@pytest.mark.parametrize("codigo,trozo", [
    ("def registrar(aria):\n    return (\n", "SyntaxError"),
    ("import modulo_que_no_existe\n", "ModuleNotFoundError"),
    ("x = 1\n", "no define registrar"),
    ("async def registrar(aria):\n    pass\n", "no async"),
    ("def registrar(aria):\n    raise SystemExit(3)\n", "SystemExit"),
    ("def registrar(aria):\n    aria.herramienta('fecha_hora', 'Choca con el núcleo.', intenciones=['x'])\n", "núcleo"),
    ("def registrar(aria):\n    aria.herramienta('mod_x', 'Sin intenciones.')\n", "intención"),
    ("def registrar(aria):\n    aria.herramienta('mod_x', 'Regex rota.', intenciones=['(abc'])\n", "intención no válida"),
    ("def registrar(aria):\n    aria.herramienta('mod_x', 'Solo negada.', intenciones=[('!abc',)])\n", "negados"),
    ("def registrar(aria):\n    aria.herramienta('mod_x', 'Uid prohibido.', {'uid': ('integer', 'x')}, intenciones=['x'])\n", "parámetro"),
    ("def registrar(aria):\n    aria.herramienta('mod_x', 'Tipo raro.', {'a': ('fecha', 'x')}, intenciones=['x'])\n", "tipo"),
    ("def registrar(aria):\n    aria.herramienta('mod_x', 'Rol raro.', roles=('root',), intenciones=['x'])\n", "roles"),
    ("def registrar(aria):\n    aria.herramienta('mod_x', 'Agente raro.', agentes=('nadie',), intenciones=['x'])\n", "agentes"),
    ("def registrar(aria):\n    aria.herramienta('Mal-Nombre', 'Nombre raro.', intenciones=['x'])\n", "nombre"),
    ("def registrar(aria):\n    @aria.herramienta('mod_x', 'Síncrona.', intenciones=['x'])\n    def f():\n        pass\n", "async"),
    ("def registrar(aria):\n    aria.config('NO_DECLARADA')\n", "no está declarada"),
    ("def registrar(aria):\n    aria.chequeo('c', intervalo_min=0)\n", "intervalo"),
    ("def registrar(aria):\n    aria.chequeo('c', severidad='fatal')\n", "severidad"),
    ("def registrar(aria):\n    aria.router(usuario=[('GET', '/../api/users')])\n", "no válida"),
    ("def registrar(aria):\n    r = aria.router(usuario=[('GET', '/no-existe')])\n    r.get('/otra')(lambda: 1)\n", "no existe"),
    ("def registrar(aria):\n    r = aria.router()\n    @r.websocket('/ws')\n    async def ws(w):\n        pass\n", "WebSocket"),
])
def test_modulo_roto_queda_en_error(cargador, codigo, trozo):
    escribir(cargador.base, "roto", manifiesto("roto"), codigo)
    res, _ = cargador()
    assert res["roto"].estado == "error" and trozo in res["roto"].error, res["roto"].error


def test_manifiesto_roto_y_sin_manifiesto(cargador):
    escribir(cargador.base, "malo", "{no es json")
    escribir(cargador.base, "vacio")
    escribir(cargador.base, "otro-id", manifiesto("distinto"))
    escribir(cargador.base, "heimdall", manifiesto("heimdall"))
    res, _ = cargador()
    assert "JSON" in res["malo"].error and "falta modulo.json" in res["vacio"].error
    assert "coincidir" in res["otro-id"].error and "integrada" in res["heimdall"].error
    assert all(m.estado == "error" for m in res.values())


def test_choque_entre_modulos(cargador):
    escribir(cargador.base, "aa", manifiesto("aa"), herramienta("mod_comun"))
    escribir(cargador.base, "bb", manifiesto("bb"), herramienta("mod_comun"))
    res, _ = cargador()
    assert res["aa"].estado == "activo"
    assert res["bb"].estado == "error" and "otro módulo" in res["bb"].error


def test_fallo_tras_registrar_no_deja_nada(cargador):
    codigo = '''
def registrar(aria):
    @aria.herramienta("mod_medio", "Se registra y luego explota.", intenciones=[r"\\bmedio\\b"], solo_lectura=True)
    async def h():
        return "x"
    @aria.chequeo("c")
    async def c():
        return []
    raise ValueError("a medias")
'''
    escribir(cargador.base, "medio", manifiesto("medio"), codigo)
    n_int, tipos = len(tools._INTENCIONES), set(avisos.TIPOS)
    res, app = cargador()
    assert res["medio"].estado == "error" and "a medias" in res["medio"].error
    assert "mod_medio" not in tools._REGISTRO and "mod_medio" not in tools.RUTINAS
    assert len(tools._INTENCIONES) == n_int and set(avisos.TIPOS) == tipos
    assert not any(k.startswith("modulo:medio") for k in avisos.chequeos())


def test_retirar_deshace_todo(cargador):
    codigo = herramienta("mod_ret", roles=("admin", "usuario")) + '''
    @aria.chequeo("c")
    async def c():
        return []
    r = aria.router(usuario=[("GET", "/x")])
    r.get("/x")(lambda: {"x": 1})
'''
    escribir(cargador.base, "ret", manifiesto("ret"), codigo)
    res, app = cargador()
    m = res["ret"]
    assert m.estado == "activo" and "mod_ret" in tools.permitidas("usuario") and "mod_ret" in tools.RUTINAS
    assert "modulo_ret" in avisos.TIPOS and "modulo:ret:c" in avisos.chequeos()
    assert permisos.permitido("usuario", "GET", "/api/modulos/ret/x")
    assert TestClient(app).get("/api/modulos/ret/x").json() == {"x": 1}
    m.retirar()
    assert "mod_ret" not in tools._REGISTRO and "mod_ret" not in tools.RUTINAS
    assert "modulo_ret" not in avisos.TIPOS and "modulo:ret:c" not in avisos.chequeos()
    assert not permisos.permitido("usuario", "GET", "/api/modulos/ret/x")
    assert TestClient(app).get("/api/modulos/ret/x").status_code == 404


def test_carpeta_inexistente_no_falla(tmp_path):
    antes = dict(modulos._CARGADOS)
    try:
        assert modulos.cargar(FastAPI(), tmp_path / "no-hay") == {}
    finally:
        modulos._CARGADOS.update(antes)


# --- SDK y herramientas --------------------------------------------------------------------------------------
def test_herramientas_del_demo_por_rol_agente_y_rutinas():
    assert "demo_eco" in tools.permitidas("usuario") and "demo_admin" not in tools.permitidas("usuario")
    assert {"demo_eco", "demo_admin"} <= tools.permitidas("admin")
    assert "demo_eco" in tools.RUTINAS and "demo_admin" not in tools.RUTINAS
    # demo_admin solo la ofrece el agente Redes (especialista); demo_eco, ARIA general.
    assert "demo_eco" in tools.generales() and "demo_admin" not in tools.generales()
    assert "demo_admin" in agentes.herramientas(agentes.obtener("redes"), "admin")
    assert "demo_admin" not in agentes.herramientas(agentes.obtener("aria"), "admin")
    assert "demo_eco" in agentes.herramientas(agentes.obtener("aria"), "usuario")


def test_intenciones_del_modulo_para_el_modelo_local():
    assert "demo_eco" in tools.relevantes("prueba demo-eco por favor")
    assert "demo_admin" in tools.relevantes("lanza demo-admin")
    assert "demo_admin" not in tools.relevantes("no lances demo-admin")
    assert not (tools.relevantes("hola, ¿qué tal?") & {"demo_eco", "demo_admin"})


def test_ejecutar_herramientas_del_modulo(monkeypatch):
    monkeypatch.setenv("DEMO_SALUDO", "hola")
    assert correr(tools.ejecutar("demo_eco", {"texto": "mundo"}, "usuario", uid=2)) == "hola: mundo"
    assert "No tienes permiso" in correr(tools.ejecutar("demo_admin", {}, "usuario"))
    # aria.Error llega tal cual al modelo
    assert correr(tools.ejecutar("demo_admin", {}, "admin")) == "fallo legible del módulo"


def test_sdk_config_y_datos(monkeypatch, tmp_path):
    a = sdk.Aria("prueba", ["OBLIG"], ["OPC"])
    monkeypatch.setenv("OBLIG", " valor ")
    monkeypatch.delenv("OPC", raising=False)
    assert a.config("OBLIG") == "valor" and a.config("OPC", "defecto") == "defecto"
    with pytest.raises(ModuloError):
        a.config("PATH")
    d = a.datos()
    assert d.is_dir() and d.parts[-2:] == ("modulos", "prueba") and str(d).startswith(str(tmp_path))


def test_chequeo_del_modulo_avisa_a_los_admins(admin):
    c = avisos.chequeos()["modulo:demo:siempre-mal"]
    assert c.tipo == "modulo_demo" and avisos.TIPOS["modulo_demo"][0] == "Módulo Demo" and c.solo_admin
    textos = correr(avisos.ejecutar_chequeo(c))
    assert set(textos) == {"algo va mal", "otra cosa"}
    lista = avisos.listar(admin["id"])
    items = lista["avisos"] if isinstance(lista, dict) else lista
    assert {a["tipo"] for a in items} == {"modulo_demo"}
    assert correr(avisos.ejecutar_chequeo(c)) == []   # no repite


# --- Permisos y API ------------------------------------------------------------------------------------------
def test_rutas_del_modulo_por_rol(admin, ana):
    u, a = cliente_de(ana), cliente_de(admin)
    assert u.get("/api/modulos/demo/hola").json() == {"hola": True}
    assert u.get("/api/modulos/demo/item/7").json() == {"n": 7}
    assert u.get("/api/modulos/demo/privado").status_code == 403
    assert u.post("/api/modulos/demo/secreto", headers={"Origin": LAN}).status_code == 403
    assert a.get("/api/modulos/demo/privado").json() == {"privado": True}
    assert a.post("/api/modulos/demo/secreto", headers={"Origin": LAN}).json() == {"secreto": True}
    # CSRF también en las rutas de módulos
    assert a.post("/api/modulos/demo/secreto", headers={"Origin": "https://malo.example"}).status_code == 403
    assert cliente_de(None).get("/api/modulos/demo/hola").status_code == 401


def test_whitelist_de_modulos_no_abre_el_nucleo():
    for metodo, ruta in [("GET", "/api/users"), ("GET", "/api/modulos/demo"), ("GET", "/api/modulosx/demo/a"),
                         ("TRACE", "/api/modulos/demo/a"), ("GET", "/api/modulos/A/a")]:
        with pytest.raises(ValueError):
            permisos.permitir_modulo(metodo, ruta)
    with pytest.raises(ValueError):
        permisos.patron_de_plantilla("/api/modulos/demo/{resto:path}")
    assert permisos.rutas_modulos_usuario() >= {("GET", "/api/modulos/demo/hola"), ("GET", "/api/modulos/demo/item/{n}")}
    assert not permisos.permitido("usuario", "GET", "/api/modulos/demo/item/1/otra")


def test_api_modulos_admin(admin, monkeypatch):
    monkeypatch.setenv("DEMO_SALUDO", "valor-que-no-debe-salir")
    r = cliente_de(admin).get("/api/modulos")
    assert r.status_code == 200 and "valor-que-no-debe-salir" not in r.text
    lista = {m["id"]: m for m in r.json()["modulos"]}
    assert lista["shield-dns"]["integrado"] and lista["heimdall"]["integrado"]
    assert "estado_bloqueador" in {h["nombre"] for h in lista["shield-dns"]["herramientas"]}
    d = lista["demo"]
    assert d["estado"] == "activo" and not d["integrado"] and d["version"] == "0.1.0"
    assert {h["nombre"] for h in d["herramientas"]} == {"demo_eco", "demo_admin"}
    assert d["env_opcional"] == [{"nombre": "DEMO_SALUDO", "definida": True}]
    assert "GET /api/modulos/demo/hola (usuario)" in d["rutas"] and "GET /api/modulos/demo/privado" in d["rutas"]
    assert lista["roto"]["estado"] == "error" and "explota" in lista["roto"]["error"]


def test_api_modulos_usuario_solo_lo_suyo_y_sin_detalles(ana):
    r = cliente_de(ana).get("/api/modulos")
    assert r.status_code == 200
    lista = r.json()["modulos"]
    assert [m["id"] for m in lista] == ["demo"]   # ni integrados ni el roto
    assert set(lista[0]) == {"id", "nombre", "descripcion", "icono", "url", "estado", "salud"}


# --- Salud ---------------------------------------------------------------------------------------------------
def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_salud_tcp_y_http():
    srv = http.server.HTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
    srv.RequestHandlerClass.log_message = lambda *a: None
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    try:
        p = srv.server_address[1]
        assert correr(modulos.comprobar_salud({"tipo": "tcp", "host": "127.0.0.1", "puerto": p})) == "ok"
        assert correr(modulos.comprobar_salud({"tipo": "http", "host": "127.0.0.1", "puerto": p, "ruta": "/",
                                               "tls": False})) == "ok"
    finally:
        srv.shutdown()
        srv.server_close()
    libre = _puerto_libre()
    assert correr(modulos.comprobar_salud({"tipo": "tcp", "host": "127.0.0.1", "puerto": libre})) == "mal"
    assert correr(modulos.comprobar_salud({"tipo": "http", "host": "127.0.0.1", "puerto": libre, "ruta": "/",
                                           "tls": False})) == "mal"
    assert correr(modulos.comprobar_salud(None)) is None


def test_salud_en_la_lista_con_cache(cargador, monkeypatch):
    escribir(cargador.base, "sano", manifiesto("sano", url="http://{host}:1/", roles=["admin", "usuario"],
                                                salud={"tipo": "tcp", "host": "127.0.0.1", "puerto": 9}))
    cargador()
    llamadas = []

    async def falsa(s):
        llamadas.append(s)
        return "ok"
    monkeypatch.setattr(modulos, "comprobar_salud", falsa)
    a = correr(modulos.listar("usuario"))
    b = correr(modulos.listar("usuario"))
    assert a == b == [{"id": "sano", "nombre": "Sano", "descripcion": "", "icono": "app", "url": "http://{host}:1/",
                       "estado": "activo", "salud": "ok"}]
    assert len(llamadas) == 1


# --- La plantilla (copiada, como haría un desarrollador) --------------------------------------------------------
@pytest.mark.skipif(not (REPO_MODULOS / "_plantilla").is_dir(), reason="sin la carpeta modulos/ del repositorio")
def test_plantilla_copiada_funciona(cargador, monkeypatch, admin, ana):
    d = cargador.base / "plantilla"
    shutil.copytree(REPO_MODULOS / "_plantilla", d)
    monkeypatch.delenv("PLANTILLA_TOKEN", raising=False)
    res, _ = cargador()
    assert res["plantilla"].estado == "sin_configurar"
    res["plantilla"].retirar()
    monkeypatch.setenv("PLANTILLA_TOKEN", "x" * 12)
    res, app = cargador(app=FastAPI())
    m = res["plantilla"]
    assert m.estado == "activo", m.error
    assert [h["nombre"] for h in m.herramientas] == ["plantilla_saludo"] and m.chequeos == ["disco-lleno"]
    assert ("GET", "/api/modulos/plantilla/estado") in m.rutas_usuario
    assert "plantilla_saludo" in tools.relevantes("saluda desde el módulo")
    assert "Hola desde la plantilla" in correr(tools.ejecutar("plantilla_saludo", {"nombre": "Ana"}, "usuario"))
    assert correr(avisos.chequeos()["modulo:plantilla:disco-lleno"].fn()) == []
    assert TestClient(app).get("/api/modulos/plantilla/estado").json()["ok"] is True


# --- Módulo de ejemplo «uptime» ---------------------------------------------------------------------------------
DNS = {"example.org": ["93.184.216.34"], "caida.example": ["93.184.216.35"], "casa.example": ["192.168.0.10"]}


@pytest.fixture
def red(monkeypatch):
    async def dns(host, puerto, type=0):
        if host not in DNS:
            raise socket.gaierror("no existe")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, puerto)) for ip in DNS[host]]

    def manejar(req: httpx.Request):
        host = req.headers["host"]
        if host == "example.org" and req.url.raw_path == b"/viejo":
            return httpx.Response(301, headers={"location": "https://casa.example/"})
        if host == "example.org":
            return httpx.Response(200, headers={"content-type": "application/octet-stream"}, content=b"x" * 10)
        return httpx.Response(503)
    monkeypatch.setattr(enlaces, "_dns", dns)
    monkeypatch.setattr(enlaces, "_transporte", httpx.MockTransport(manejar))


def test_enlaces_comprobar(red):
    r = correr(enlaces.comprobar("https://example.org/"))
    assert r["ok"] and r["estado"] == 200 and r["url"] == "https://example.org/" and r["ms"] >= 0
    r = correr(enlaces.comprobar("https://caida.example/"))
    assert not r["ok"] and r["estado"] == 503
    with pytest.raises(enlaces.EnlaceError, match="red de casa|privada"):
        correr(enlaces.comprobar("https://example.org/viejo"))     # redirección a casa: se revalida
    with pytest.raises(enlaces.EnlaceError):
        correr(enlaces.comprobar("http://192.168.0.1/"))


uptime = pytest.mark.skipif(not (REPO_MODULOS / "uptime").is_dir(), reason="sin la carpeta modulos/ del repositorio")


@uptime
def test_uptime_herramienta(cargador, red, monkeypatch, ana, admin):
    monkeypatch.delenv("UPTIME_URLS", raising=False)
    res, app = cargador(directorio=REPO_MODULOS, habilitados={"uptime"})
    m = res["uptime"]
    assert m.estado == "activo", m.error
    assert all(x.estado == "desactivado" for k, x in res.items() if k != "uptime")
    assert m.chequeos == []   # sin UPTIME_URLS, sin avisos
    assert "comprobar_web" in tools.permitidas("usuario") and "comprobar_web" in tools.RUTINAS
    assert "comprobar_web" in agentes.herramientas(agentes.obtener("redes"), "usuario")
    ok = correr(tools.ejecutar("comprobar_web", {"url": "example.org"}, "usuario"))
    assert ok.startswith("https://example.org responde (código 200)") and " ms" in ok
    assert "problemas" in correr(tools.ejecutar("comprobar_web", {"url": "https://caida.example"}, "usuario"))
    assert "no responde" in correr(tools.ejecutar("comprobar_web", {"url": "http://192.168.0.1"}, "usuario"))
    assert "no responde" in correr(tools.ejecutar("comprobar_web", {"url": "https://no-existe.example"}, "admin"))
    # El modelo local la recibe solo si hay web + pregunta de disponibilidad
    assert "comprobar_web" in tools.relevantes("¿responde https://example.org?")
    assert "comprobar_web" in tools.relevantes("¿está caída github.com?")
    assert "comprobar_web" not in tools.relevantes("¿qué tiempo hace mañana?")
    # Endpoint de estado: solo admin (no está en la lista de usuario)
    assert ("GET", "/api/modulos/uptime/estado") in m.rutas and not m.rutas_usuario


@uptime
def test_uptime_chequeo(cargador, red, monkeypatch):
    monkeypatch.setenv("UPTIME_URLS", "example.org, https://caida.example ,http://192.168.0.1")
    monkeypatch.setenv("UPTIME_INTERVALO_MIN", "15")
    res, app = cargador(directorio=REPO_MODULOS, habilitados={"uptime"})
    assert res["uptime"].chequeos == ["webs"]
    c = avisos.chequeos()["modulo:uptime:webs"]
    assert c.intervalo_s == 900 and c.confirmaciones == 2 and c.solo_admin
    problemas = correr(c.fn())
    assert {p.clave for p in problemas} == {"https://caida.example", "http://192.168.0.1"}
    assert c.texto_ok("https://caida.example") == "https://caida.example vuelve a responder."
    estado = TestClient(app).get("/api/modulos/uptime/estado").json()
    assert estado["intervalo_min"] == 15 and len(estado["resultados"]) == 3
