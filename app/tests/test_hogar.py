"""Hogar: luces Govee, cámaras Tapo y router TP-Link. Sin red: Govee con MockTransport y los demás con dobles."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from aria import api_hogar, auth, config, hogar_govee, hogar_router, hogar_tapo, main, tools, usuarios

LAN = "https://192.168.1.50"
CLAVE_FALSA = "clave-govee-de-prueba-123"
CLIENTE_HTTP = httpx.AsyncClient   # el real, antes de cualquier sustitución
PASS_FALSA = "contrasena-router-de-prueba"


def cliente(u):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    monkeypatch.setattr(hogar_govee, "_cache", {"cuando": 0.0, "dispositivos": []})
    monkeypatch.setattr(hogar_govee, "_ultimo", {})
    monkeypatch.setattr(hogar_router, "_cache", {"cuando": 0.0, "estado": None, "completos": []})
    monkeypatch.setattr(hogar_tapo, "_conexiones", {})
    monkeypatch.setattr(hogar_tapo, "_conocidas", set())
    monkeypatch.setattr(api_hogar, "_acciones", [])
    from aria import hogar_cache
    hogar_cache.limpiar()

    async def sin_espera(_segundos, result=None):
        return result
    monkeypatch.setattr(hogar_govee.asyncio, "sleep", sin_espera)


# --- Govee -------------------------------------------------------------------------------------------------------
def _govee(monkeypatch, respuestas: dict, enviados: list | None = None):
    """respuestas: ruta -> función(request) -> httpx.Response."""
    monkeypatch.setattr(config, "GOVEE_API_KEY", CLAVE_FALSA)
    def manejar(r: httpx.Request):
        assert r.headers["Govee-API-Key"] == CLAVE_FALSA
        if enviados is not None and r.content:
            enviados.append(json.loads(r.content))
        return respuestas[r.url.path.rsplit("/v1/", 1)[1]](r)
    monkeypatch.setattr(hogar_govee.httpx, "AsyncClient", lambda **kw: CLIENTE_HTTP(transport=httpx.MockTransport(manejar), **kw))


DISPOSITIVOS = {"code": 200, "message": "success", "data": [
    {"sku": "H6199", "device": "AA:BB", "deviceName": "Tira del Salón"},
    {"sku": "H6008", "device": "CC:DD", "deviceName": "Bombilla cocina"}]}


def _estado(r):
    disp = json.loads(r.content)["payload"]["device"]
    caps = [{"type": "devices.capabilities.online", "instance": "online", "state": {"value": disp == "AA:BB"}},
            {"type": "devices.capabilities.on_off", "instance": "powerSwitch", "state": {"value": 1}},
            {"type": "devices.capabilities.range", "instance": "brightness", "state": {"value": 50}},
            {"type": "devices.capabilities.color_setting", "instance": "colorRgb", "state": {"value": 0xFF0000}}]
    return httpx.Response(200, json={"requestId": "x", "msg": "success", "code": 200,
                                     "payload": {"sku": "H6199", "device": disp, "capabilities": caps}})


def test_govee_lista_luces_con_su_estado(monkeypatch):
    _govee(monkeypatch, {"user/devices": lambda r: httpx.Response(200, json=DISPOSITIVOS), "device/state": _estado})
    luces = asyncio.run(hogar_govee.luces())
    assert luces[0] == {"nombre": "Tira del Salón", "id": "AA:BB", "sku": "H6199", "encendida": True, "brillo": 50,
                        "color": "#ff0000", "en_linea": True}
    assert luces[1]["en_linea"] is False


def test_govee_cambia_encendido_brillo_y_color(monkeypatch):
    enviados = []
    ok = lambda r: httpx.Response(200, json={"requestId": "x", "msg": "success", "code": 200, "payload": {}})
    _govee(monkeypatch, {"user/devices": lambda r: httpx.Response(200, json=DISPOSITIVOS), "device/control": ok}, enviados)
    assert asyncio.run(hogar_govee.cambiar("AA:BB", encendida=False, brillo=30, color=0x3366FF)) == {"ok": True}
    capacidades = [e["payload"]["capability"] for e in enviados]
    assert capacidades == [
        {"type": "devices.capabilities.on_off", "instance": "powerSwitch", "value": 0},
        {"type": "devices.capabilities.range", "instance": "brightness", "value": 30},
        {"type": "devices.capabilities.color_setting", "instance": "colorRgb", "value": 0x3366FF}]
    assert all(e["payload"]["sku"] == "H6199" and e["requestId"] for e in enviados)


def test_govee_errores_y_reintento_tras_429(monkeypatch):
    llamadas = []

    def con_429(r):
        llamadas.append(1)
        return httpx.Response(429) if len(llamadas) == 1 else httpx.Response(200, json=DISPOSITIVOS)
    _govee(monkeypatch, {"user/devices": con_429})
    assert len(asyncio.run(hogar_govee._listar_bruto())) == 2 and len(llamadas) == 2
    hogar_govee._cache["cuando"] = 0.0
    _govee(monkeypatch, {"user/devices": lambda r: httpx.Response(200, json={"code": 401, "message": "Unauthorized"})})
    with pytest.raises(hogar_govee.GoveeError):
        asyncio.run(hogar_govee._listar_bruto())
    with pytest.raises(hogar_govee.GoveeError):
        asyncio.run(hogar_govee.cambiar("ZZ", encendida=True))


# --- Router -------------------------------------------------------------------------------------------------------
class RouterFalso:
    def __init__(self, falla=False):
        self.falla, self.log = falla, []

    def authorize(self):
        self.log.append("authorize")

    def logout(self):
        self.log.append("logout")

    def get_status(self):
        from tplinkrouterc6u import Connection

        class Disp:
            def __init__(self, nombre, ip, tipo, mac="AA-BB-CC-DD-EE-FF"):
                self.hostname, self.ipaddress, self.macaddress, self.type, self.active = nombre, ip, mac, tipo, True

        class Estado:
            clients_total, guest_2g_enable, guest_5g_enable = 2, False, None
            devices = [Disp("Portátil", "192.168.1.20", Connection.HOST_5G), Disp("Tele", "192.168.1.21", Connection.WIRED, "AA-BB-CC-DD-EE-01")]
        if self.falla:
            raise RuntimeError("se cayó a mitad")
        return Estado()

    def get_firmware(self):
        class F:
            model = "Router de prueba"
        return F()

    def set_wifi(self, banda, activa):
        self.log.append((banda.name, activa))

    def reboot(self):
        self.log.append("reboot")

    def get_ipv4_dhcp_leases(self):
        class Concesion:
            hostname, macaddress, ipaddress = "Xiaomi-dormido ", "AA-BB-CC-00-00-09", "192.168.1.29"
        return [Concesion()]


def _router(monkeypatch, falso):
    import tplinkrouterc6u
    monkeypatch.setattr(config, "ROUTER_PASSWORD", PASS_FALSA)
    monkeypatch.setattr(tplinkrouterc6u.TplinkRouterProvider, "get_client", staticmethod(lambda *a, **kw: falso))


def test_router_estado_y_siempre_cierra_sesion(monkeypatch):
    falso = RouterFalso()
    _router(monkeypatch, falso)
    e = asyncio.run(hogar_router.estado())
    assert e["modelo"] == "Router de prueba" and e["conectados"] == 2 and e["invitados_24"] is False
    assert "invitados_5" not in e   # el router no lo da: no se inventa
    assert {c["banda"] for c in e["clientes"]} == {"5 GHz", "cable"} and e["clientes"][0]["mac"] == "DD:EE:FF"
    assert falso.log == ["authorize", "logout"]
    roto = RouterFalso(falla=True)
    _router(monkeypatch, roto)
    hogar_router._cache["cuando"] = 0.0
    with pytest.raises(hogar_router.RouterError) as error:
        asyncio.run(hogar_router.estado())
    assert roto.log == ["authorize", "logout"]          # la sesión se cierra aunque falle (si no, echa a Tether)
    assert PASS_FALSA not in str(error.value)


def test_router_invitados_en_las_dos_bandas_y_reinicio(monkeypatch):
    falso = RouterFalso()
    _router(monkeypatch, falso)
    assert asyncio.run(hogar_router.invitados(True)) == {"activa": True}
    assert ("GUEST_2G", True) in falso.log and ("GUEST_5G", True) in falso.log
    asyncio.run(hogar_router.reiniciar())
    assert "reboot" in falso.log and falso.log[-1] == "logout"


# --- Cámaras Tapo -------------------------------------------------------------------------------------------------
class Mascara:
    def __init__(self):
        self.enabled = False

    async def set_enabled(self, si):
        self.enabled = si


class CamaraFalsa:
    def __init__(self):
        self.model, self.alias, self.modules = "C520WS", "Jardín", {"LensMask": Mascara()}

    async def update(self):
        return None


def _tapo(monkeypatch, camara):
    monkeypatch.setattr(config, "TAPO_USUARIO", "usuario@example.com")
    monkeypatch.setattr(config, "TAPO_PASSWORD", PASS_FALSA)
    monkeypatch.setattr(config, "TAPO_CAMARAS", ["192.168.1.30"])

    async def conectar(ip):
        return camara
    monkeypatch.setattr(hogar_tapo, "_conectar", conectar)


def test_tapo_estado_y_privacidad(monkeypatch):
    camara = CamaraFalsa()
    _tapo(monkeypatch, camara)
    assert asyncio.run(hogar_tapo.camaras()) == [{"ip": "192.168.1.30", "modelo": "C520WS", "nombre": "Jardín",
                                                  "en_linea": True, "ptz": False, "privacidad": False}]
    assert asyncio.run(hogar_tapo.privacidad("192.168.1.30", True))["privacidad"] is True
    with pytest.raises(hogar_tapo.TapoError):
        asyncio.run(hogar_tapo.privacidad("192.168.1.99", True))   # IP que no es una cámara conocida


# --- API y permisos -----------------------------------------------------------------------------------------------
def test_api_por_rol_y_sin_credenciales(monkeypatch):
    _govee(monkeypatch, {"user/devices": lambda r: httpx.Response(200, json=DISPOSITIVOS), "device/state": _estado})
    _router(monkeypatch, RouterFalso())
    _tapo(monkeypatch, CamaraFalsa())
    admin = usuarios.por_identificador("admin")
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    d = cliente(admin).get("/api/hogar").json()
    assert set(d) == {"luces", "router", "camaras"} and d["router"]["datos"]["conectados"] == 2
    texto = json.dumps(d)
    assert CLAVE_FALSA not in texto and PASS_FALSA not in texto
    c = cliente(ana)
    assert set(c.get("/api/hogar").json()) == {"luces"}              # un usuario no ve router ni cámaras
    assert c.post("/api/hogar/router/reiniciar").status_code == 403
    assert c.post("/api/hogar/router/invitados", json={"activa": True}).status_code == 403
    assert c.post("/api/hogar/camaras/privacidad", json={"ip": "192.168.1.30", "activa": True}).status_code == 403
    assert c.post("/api/hogar/luces/AA:BB", json={"brillo": 101}).status_code == 400
    assert c.post("/api/hogar/luces/AA:BB", json={"color": "rojo"}).status_code == 400


def test_sin_configurar_lo_dice(monkeypatch):
    for nombre in ("GOVEE_API_KEY", "TAPO_USUARIO", "TAPO_PASSWORD", "ROUTER_PASSWORD"):
        monkeypatch.setattr(config, nombre, "")
    d = cliente(usuarios.por_identificador("admin")).get("/api/hogar").json()
    assert d["luces"]["configurado"] is False and d["router"]["configurado"] is False
    assert d["camaras"]["configurado"] is False


# --- Herramientas del chat ----------------------------------------------------------------------------------------
def test_herramienta_luces_busca_sin_acentos(monkeypatch):
    cambios = []

    async def luces():
        return [{"nombre": "Tira del Salón", "id": "AA:BB", "encendida": True},
                {"nombre": "Bombilla cocina", "id": "CC:DD", "encendida": False}]

    async def cambiar(ident, encendida=None, brillo=None, color=None):
        cambios.append((ident, encendida, brillo, color))
        return {"ok": True}
    monkeypatch.setattr(hogar_govee, "luces", luces)
    monkeypatch.setattr(hogar_govee, "cambiar", cambiar)
    assert "Tira del Salón" in asyncio.run(tools.luces("salon", encendida=False))
    assert cambios == [("AA:BB", False, None, None)]
    asyncio.run(tools.luces("", encendida=False))                    # «apaga todas»
    assert len(cambios) == 3
    assert "luces" in tools.permitidas("usuario") and "router_invitados" not in tools.permitidas("usuario")
    assert "luces" not in tools.RUTINAS                               # una rutina programada no toca la casa


def test_herramienta_camara_sin_ip(monkeypatch):
    _tapo(monkeypatch, CamaraFalsa())
    assert asyncio.run(tools.camara_privacidad(True)) == "He tapado Jardín."
    assert "camara_privacidad" not in tools.permitidas("usuario")


# --- Vigilancia automática -----------------------------------------------------------------------------------------
MOVILES = [{"mac": "AA:BB:CC:00:00:01", "nombre": "Pixel", "ip": "192.168.1.40"},
           {"mac": "AA:BB:CC:00:00:02", "nombre": "Xiaomi", "ip": "192.168.1.41"},
           {"mac": "AA:BB:CC:00:00:03", "nombre": "Galaxy", "ip": "192.168.1.42"}]


def _vigilancia(monkeypatch, conectados: list, falla_router=False):
    from aria import hogar_vigilancia as hv
    hv.iniciar()
    estado = {"conectados": conectados, "falla": falla_router, "ping": set()}
    monkeypatch.setattr(hv, "_responde", lambda ip: ip in estado["ping"])
    cambios, emitidos = [], []

    async def router_conectados():
        if estado["falla"]:
            raise hogar_router.RouterError("no responde")
        return list(estado["conectados"])

    async def privacidad(ip, activa):
        cambios.append((ip, activa))
        return {}

    async def emitir(tipo, severidad, texto, enlace="", destinatarios=None, **kw):
        emitidos.append((tipo, texto))
        return []
    monkeypatch.setattr(hogar_router, "conectados", router_conectados)
    monkeypatch.setattr(hogar_tapo, "privacidad", privacidad)
    monkeypatch.setattr(hv.avisos, "emitir", emitir)
    hv.configurar({"activa": True, "minutos": 10, "camaras": ["192.168.1.30"],
                   "moviles": [hv.ident(m["mac"]) for m in MOVILES]}, MOVILES)
    return hv, estado, cambios, emitidos


def test_vigilancia_destapa_solo_cuando_todos_llevan_10_min_fuera_y_tapa_al_volver(monkeypatch):
    import time
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, MOVILES)
    t = time.time()
    assert asyncio.run(hv.ciclo(t)) is None                              # todos en casa
    estado["conectados"] = [MOVILES[2]]                                  # se van dos; queda el Galaxy
    assert asyncio.run(hv.ciclo(t + 30 * 60)) is None
    estado["conectados"] = []                                            # se va el último
    assert asyncio.run(hv.ciclo(t + 31 * 60)) is None                    # aún no han pasado 10 min desde que se fue
    assert asyncio.run(hv.ciclo(t + 42 * 60)) == "fuera"
    assert cambios == [("192.168.1.30", False)] and emitidos[0][0] == "vigilancia"
    assert asyncio.run(hv.ciclo(t + 50 * 60)) is None                    # no repite
    estado["conectados"] = [MOVILES[1]]
    assert asyncio.run(hv.ciclo(t + 60 * 60)) == "casa"
    assert cambios[-1] == ("192.168.1.30", True) and "Xiaomi" in emitidos[-1][1]


def test_vigilancia_no_toca_nada_si_el_router_no_responde(monkeypatch):
    import time
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, [], falla_router=True)
    assert asyncio.run(hv.ciclo(time.time() + 3 * 3600)) is None
    assert cambios == [] and emitidos == []


def test_vigilancia_un_movil_nunca_visto_cuenta_desde_que_se_activa(monkeypatch):
    import time
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, [])
    t = time.time()
    assert asyncio.run(hv.ciclo(t + 60)) is None                         # recién activada: no destapa de golpe
    assert asyncio.run(hv.ciclo(t + 11 * 60)) == "fuera"


def test_vigilancia_valida_y_no_envia_macs_enteras(monkeypatch):
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, MOVILES)
    with pytest.raises(ValueError):
        hv.configurar({"minutos": 2}, MOVILES)
    with pytest.raises(ValueError):
        hv.configurar({"moviles": ["inventado"]}, MOVILES)
    with pytest.raises(ValueError):
        hv.configurar({"moviles": []}, MOVILES)                          # activa y sin móviles: no
    monkeypatch.setattr(config, "ROUTER_PASSWORD", PASS_FALSA)
    admin = usuarios.por_identificador("admin")
    d = cliente(admin).get("/api/hogar/vigilancia").json()
    assert d["activa"] is True and [m["nombre"] for m in d["moviles"]] == ["Pixel", "Xiaomi", "Galaxy"]
    assert "AA:BB:CC" not in json.dumps(d)
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    assert cliente(ana).get("/api/hogar/vigilancia").status_code == 403
    assert cliente(ana).post("/api/hogar/vigilancia", json={"activa": False}).status_code == 403


# --- Vídeo de las cámaras (go2rtc) ----------------------------------------------------------------------------------
def test_config_go2rtc_con_clave_codificada_y_permisos_640(monkeypatch, tmp_path):
    import os, stat
    from aria import hogar_camaras
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "TAPO_USUARIO", "usuario@example.com")
    monkeypatch.setattr(config, "TAPO_PASSWORD", "con@raro/#%")
    monkeypatch.setattr(config, "TAPO_CAMARAS", ["192.168.1.30", "192.168.1.31"])
    assert hogar_camaras.escribir_config() is True
    texto = hogar_camaras.ruta_config().read_text()
    assert "c1: tapo://con%40raro%2F%23%25@192.168.1.30" in texto and "c2: tapo://" in texto
    assert 'rtsp:\n  listen: ""' in texto                                      # nada escucha fuera de la API interna
    assert stat.S_IMODE(os.stat(hogar_camaras.ruta_config()).st_mode) == 0o640
    assert hogar_camaras.escribir_config() is False                          # sin cambios: no hay que reiniciar
    assert hogar_camaras.flujo("192.168.1.31") == "c2" and hogar_camaras.flujo("192.168.1.99") is None
    monkeypatch.setattr(config, "TAPO_PASSWORD", "")
    hogar_camaras.escribir_config()
    assert "tapo://" not in hogar_camaras.ruta_config().read_text()          # sin credenciales, sin flujos


def test_foto_y_directo_solo_admin_y_solo_camaras_conocidas(monkeypatch):
    from aria import hogar_camaras
    monkeypatch.setattr(config, "TAPO_USUARIO", "usuario@example.com")
    monkeypatch.setattr(config, "TAPO_PASSWORD", PASS_FALSA)
    monkeypatch.setattr(config, "TAPO_CAMARAS", ["192.168.1.30"])

    async def foto(ip, max_edad=0):
        return b"\xff\xd8imagen"
    monkeypatch.setattr(hogar_camaras, "foto", foto)
    admin = usuarios.por_identificador("admin")
    r = cliente(admin).get("/api/hogar/camaras/foto?ip=192.168.1.30")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.headers["cache-control"] == "no-store"
    assert cliente(admin).get("/api/hogar/camaras/foto?ip=192.168.1.99").status_code == 404
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    assert cliente(ana).get("/api/hogar/camaras/foto?ip=192.168.1.30").status_code == 403
    from starlette.websockets import WebSocketDisconnect
    for quien, ip in ((ana, "192.168.1.30"), (admin, "192.168.1.99")):
        c = cliente(quien)
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(f"/api/hogar/camaras/directo?ip={ip}", headers={"origin": LAN}) as ws:
                ws.receive_text()


def test_vigilancia_el_ping_cubre_al_movil_que_falta_en_la_lista_de_la_malla(monkeypatch):
    import time
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, MOVILES)
    t = time.time()
    asyncio.run(hv.ciclo(t))                                             # aprende las IP de los tres
    estado["conectados"] = []                                            # el router no lista a nadie…
    estado["ping"] = {"192.168.1.40"}                                    # …pero el Pixel contesta (otro nodo)
    assert asyncio.run(hv.ciclo(t + 30 * 60)) is None and cambios == []  # no se destapa
    estado["ping"] = set()
    asyncio.run(hv.ciclo(t + 31 * 60))
    assert asyncio.run(hv.ciclo(t + 42 * 60)) == "fuera"
    estado["falla"], estado["ping"] = True, {"192.168.1.41"}            # router caído, pero el Xiaomi contesta
    assert asyncio.run(hv.ciclo(t + 50 * 60)) == "casa"                  # para taparla basta con el ping


def test_vigilancia_sin_router_nunca_destapa_aunque_nadie_conteste(monkeypatch):
    import time
    hv, estado, cambios, emitidos = _vigilancia(monkeypatch, [], falla_router=True)
    assert asyncio.run(hv.ciclo(time.time() + 5 * 3600)) is None and cambios == []


def test_router_conocidos_incluye_concesiones_dhcp(monkeypatch):
    _router(monkeypatch, RouterFalso())
    nombres = {c["nombre"] for c in asyncio.run(hogar_router.conocidos())}
    assert {"Portátil", "Tele", "Xiaomi-dormido"} <= nombres        # el que duerme también se puede elegir


def test_ajustes_y_movimiento_de_camaras(monkeypatch):
    class Modulo:
        def __init__(self): self.enabled, self.led, self.llamadas = False, True, []
        async def set_enabled(self, si): self.enabled = si
        async def set_led(self, si): self.led = si
        async def move(self, *, pan, tilt): self.llamadas.append((pan, tilt))

    class Bateria:
        battery_percent = 64

    camara = CamaraFalsa()
    mov, motor = Modulo(), Modulo()
    camara.modules.update({"MotionDetection": mov, "Led": mov, "PanTilt": motor, "Battery": Bateria()})
    _tapo(monkeypatch, camara)
    fila = asyncio.run(hogar_tapo.camaras())[0]
    assert fila["ptz"] is True and fila["bateria"] == 64 and fila["movimiento"] is False and fila["led"] is True
    assert asyncio.run(hogar_tapo.ajustar("192.168.1.30", "movimiento", True))["movimiento"] is True
    asyncio.run(hogar_tapo.mover("192.168.1.30", "izquierda"))
    assert motor.llamadas == [(hogar_tapo.PASO_GIRO, 0)]
    with pytest.raises(hogar_tapo.TapoError):
        asyncio.run(hogar_tapo.ajustar("192.168.1.30", "borrar_tarjeta", True))
    with pytest.raises(hogar_tapo.TapoError):
        asyncio.run(hogar_tapo.mover("192.168.1.99", "arriba"))
    admin = usuarios.por_identificador("admin")
    c = cliente(admin)
    assert c.post("/api/hogar/camaras/mover", json={"ip": "192.168.1.30", "direccion": "girar_loco"}).status_code == 400
    assert c.post("/api/hogar/camaras/ajuste", json={"ip": "192.168.1.30", "campo": "led", "valor": False}).json()["camara"]["led"] is False
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    assert cliente(ana).post("/api/hogar/camaras/mover", json={"ip": "192.168.1.30", "direccion": "arriba"}).status_code == 403


def test_miniatura_reutiliza_la_foto_reciente(monkeypatch):
    from aria import hogar_camaras
    monkeypatch.setattr(config, "TAPO_CAMARAS", ["192.168.1.30"])
    monkeypatch.setattr(hogar_camaras, "_fotos", {})
    llamadas = []

    async def nueva(nombre):
        llamadas.append(nombre)
        return b"\\xff\\xd8x"
    monkeypatch.setattr(hogar_camaras, "_foto_nueva", nueva)
    asyncio.run(hogar_camaras.foto("192.168.1.30", 600))
    asyncio.run(hogar_camaras.foto("192.168.1.30", 600))          # la segunda no despierta a la cámara
    asyncio.run(hogar_camaras.foto("192.168.1.30"))               # el directo/foto pedida sí
    assert llamadas == ["c1", "c1"]


def test_proxy_grabaciones_filtra_ip_y_rol(monkeypatch):
    from aria import hogar_grabaciones
    monkeypatch.setattr(config, "TAPO_CAMARAS", ["192.168.1.30"])
    llamadas = []

    async def consultar(ruta, parametros):
        llamadas.append((ruta, parametros))
        return httpx.Response(200, json={"dias": ["2026-07-16"]})

    monkeypatch.setattr(hogar_grabaciones, "consultar", consultar)
    admin = usuarios.por_identificador("admin")
    assert cliente(admin).get("/api/hogar/camaras/grabaciones/dias?ip=192.168.1.30").json() == {"dias": ["2026-07-16"]}
    assert cliente(admin).get("/api/hogar/camaras/grabaciones/dias?ip=192.168.1.99").status_code == 404
    ana = usuarios.crear("ana-grabaciones@example.com", "Ana", "usuario", "clave-larga-ana")
    assert cliente(ana).get("/api/hogar/camaras/grabaciones/dias?ip=192.168.1.30").status_code == 403
    assert llamadas == [("/dias", {"cam": "c1"})]


def test_proxy_grabacion_reenvia_range_y_respuesta(monkeypatch):
    from aria import hogar_grabaciones
    monkeypatch.setattr(config, "TAPO_CAMARAS", ["192.168.1.30"])

    class Respuesta:
        status_code = 206
        headers = {"content-type": "video/mp4", "content-length": "4", "content-range": "bytes 2-5/10",
                   "accept-ranges": "bytes", "cache-control": "no-store"}

        async def aread(self): return b"abcd"
        async def aiter_bytes(self): yield b"abcd"

    class Stream:
        def __init__(self): self.respuesta = Respuesta()
        async def __aenter__(self): return self.respuesta
        async def __aexit__(self, *args): pass

    recibido = []
    def stream(ruta, parametros, rango):
        recibido.append((ruta, parametros, rango))
        return Stream()

    monkeypatch.setattr(hogar_grabaciones, "cliente_stream", stream)
    admin = usuarios.por_identificador("admin")
    r = cliente(admin).get("/api/hogar/camaras/grabaciones/clip?ip=192.168.1.30&dia=2026-07-16&inicio=10&fin=20",
                     headers={"Range": "bytes=2-5"})
    assert r.status_code == 206 and r.content == b"abcd"
    assert r.headers["content-range"] == "bytes 2-5/10" and recibido[-1][2] == "bytes=2-5"
    assert recibido[-1][1]["dia"] == "2026-07-16"                      # solo se valida ese día en la cámara
    assert cliente(admin).get("/api/hogar/camaras/grabaciones/clip?ip=192.168.1.30&inicio=10&fin=20").status_code == 400


def test_cache_responde_con_lo_ultimo_y_refresca_detras(monkeypatch):
    from aria import hogar_cache
    import time
    llamadas = []

    async def lento():
        llamadas.append(1)
        return len(llamadas)

    async def flujo():
        assert await hogar_cache.obtener("x", lento, fresco=60) == 1
        assert await hogar_cache.obtener("x", lento, fresco=60) == 1          # fresco: ni llama
        hogar_cache._datos["x"] = (time.monotonic() - 120, 1)                   # viejo pero válido
        assert await hogar_cache.obtener("x", lento, fresco=60) == 1          # responde ya con lo viejo…
        await hogar_cache._tareas["x"]
        assert hogar_cache._datos["x"][1] == 2                                  # …y lo refrescó detrás
        hogar_cache.invalidar("x")
        assert await hogar_cache.obtener("x", lento) == 3
    asyncio.run(flujo())


def test_secciones_por_separado_y_por_rol(monkeypatch):
    _govee(monkeypatch, {"user/devices": lambda r: httpx.Response(200, json=DISPOSITIVOS), "device/state": _estado})
    _router(monkeypatch, RouterFalso())
    _tapo(monkeypatch, CamaraFalsa())
    admin = usuarios.por_identificador("admin")
    c = cliente(admin)
    assert c.get("/api/hogar/luces").json()["datos"][0]["nombre"] == "Tira del Salón"
    assert c.get("/api/hogar/camaras").json()["datos"][0]["nombre"] == "Jardín"
    assert c.get("/api/hogar/router").json()["datos"]["conectados"] == 2
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    a = cliente(ana)
    assert a.get("/api/hogar/luces").status_code == 200
    assert a.get("/api/hogar/camaras").status_code == 403 and a.get("/api/hogar/router").status_code == 403


def test_config_go2rtc_webrtc_solo_con_ip_de_casa(monkeypatch, tmp_path):
    from aria import hogar_camaras
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "TAPO_USUARIO", "usuario@example.com")
    monkeypatch.setattr(config, "TAPO_PASSWORD", "x")
    monkeypatch.setattr(config, "TAPO_CAMARAS", ["192.168.1.30"])
    monkeypatch.setattr(config, "LAN_IP", "127.0.0.1")
    hogar_camaras.escribir_config()
    assert 'webrtc:\n  listen: ""' in hogar_camaras.ruta_config().read_text()          # sin IP de casa: apagado
    monkeypatch.setattr(config, "LAN_IP", "192.168.1.50")
    hogar_camaras.escribir_config()
    texto = hogar_camaras.ruta_config().read_text()
    assert 'webrtc:\n  listen: ":8555"\n  candidates:\n    - 192.168.1.50:8555' in texto
