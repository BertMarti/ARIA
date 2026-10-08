"""Control parental con un Pi-hole FALSO (httpx.MockTransport): nada de red. Cubre el estado deseado, los
horarios, la reconciliación idempotente, las protecciones, las herramientas del agente y la API."""
import asyncio
import json
import re
import time
from datetime import datetime
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient

from aria import auth, avisos, config, control, db, main, red, shield, telegram as tg, tiempo, tools, usuarios
from contextlib import closing

LAN = "https://192.168.1.50"


class FalsoPihole:
    """Lo mínimo de la API v6: /api/auth, /api/groups, /api/clients, /api/domains/deny/regex y /api/network/devices."""

    def __init__(self):
        self.grupos = [{"name": "Default", "id": 0, "enabled": True, "comment": ""}]
        self.clientes = []
        self.dominios = []
        self.escrituras = []          # (método, ruta)
        self.ignorar_grupos = False   # simula un Pi-hole que mete la regla en Default
        self.caido = False

    def handler(self, req: httpx.Request) -> httpx.Response:
        if self.caido:
            raise httpx.ConnectError("caído")
        ruta, m = unquote(req.url.path), req.method
        cuerpo = json.loads(req.content) if req.content else {}
        if ruta == "/api/auth":
            return httpx.Response(200, json={"session": {"sid": "sid-falso"}}) if m == "POST" else httpx.Response(204)
        if req.headers.get("X-FTL-SID") != "sid-falso":
            return httpx.Response(401, json={})
        if ruta == "/api/network/devices":
            return httpx.Response(200, json={"devices": []})
        if m != "GET":
            self.escrituras.append((m, ruta))
        if ruta == "/api/groups":
            if m == "GET":
                return httpx.Response(200, json={"groups": self.grupos})
            g = {"name": cuerpo["name"], "id": max(x["id"] for x in self.grupos) + 1, "enabled": True,
                 "comment": cuerpo.get("comment", "")}
            self.grupos.append(g)
            return httpx.Response(201, json={"groups": [g]})
        if ruta == "/api/clients":
            if m == "GET":
                return httpx.Response(200, json={"clients": self.clientes})
            c = {"client": cuerpo["client"], "comment": cuerpo.get("comment", ""), "groups": cuerpo.get("groups", [0])}
            self.clientes.append(c)
            return httpx.Response(201, json={"clients": [c]})
        if ruta.startswith("/api/clients/"):
            ip = ruta.rsplit("/", 1)[1]
            c = next(x for x in self.clientes if x["client"] == ip)
            if m == "DELETE":
                self.clientes.remove(c)
                return httpx.Response(204)
            c.update(comment=cuerpo["comment"], groups=cuerpo["groups"])
            return httpx.Response(200, json={"clients": [c]})
        if ruta == "/api/domains/deny/regex":
            if m == "GET":
                return httpx.Response(200, json={"domains": self.dominios})
            d = {"domain": cuerpo["domain"], "comment": cuerpo.get("comment", ""), "enabled": cuerpo["enabled"],
                 "groups": [0] if self.ignorar_grupos else cuerpo["groups"], "kind": "regex", "type": "deny"}
            self.dominios.append(d)
            return httpx.Response(201, json={"domains": [d]})
        if ruta.startswith("/api/domains/deny/regex/"):
            dom = ruta[len("/api/domains/deny/regex/"):]
            d = next(x for x in self.dominios if x["domain"] == dom)
            if m == "DELETE":
                self.dominios.remove(d)
                return httpx.Response(204)
            d.update(comment=cuerpo["comment"], enabled=cuerpo["enabled"],
                     groups=[0] if self.ignorar_grupos else cuerpo["groups"])
            return httpx.Response(200, json={"domains": [d]})
        return httpx.Response(404, json={})

    def gid(self, nombre):
        return next(g["id"] for g in self.grupos if g["name"] == nombre)

    def propios(self):
        return {c["client"]: sorted(c["groups"]) for c in self.clientes}


@pytest.fixture
def ph(monkeypatch):
    f = FalsoPihole()
    real = httpx.AsyncClient

    def fabrica(*a, **kw):
        kw["transport"] = httpx.MockTransport(f.handler)
        return real(*a, **kw)
    monkeypatch.setattr(shield.httpx, "AsyncClient", fabrica)
    monkeypatch.setattr(config, "SHIELD_URL", "http://pihole.test")
    monkeypatch.setattr(config, "SHIELD_PASSWORD", "x")
    monkeypatch.setattr(shield, "_sid", None)
    return f


def inventario(clave, ip, alias=None, nombre=None):
    with closing(db._con()) as con, con:
        con.execute("INSERT OR REPLACE INTO red_inventario (clave, mac, ip, nombre, alias, conocido, primera_vez, ultima_vez) "
                    "VALUES (?,?,?,?,?,1,1,1)", (clave, None if clave.startswith("ip-") else clave, ip, nombre, alias))
    return clave


@pytest.fixture
def ipad():
    return inventario("AA:BB:CC:00:00:01", "192.168.0.50", "iPad")


def correr(c):
    return asyncio.run(c)


def ts(y, mes, d, h, mi=0):
    return datetime(y, mes, d, h, mi, tzinfo=tiempo.zona()).timestamp()


# 2026-10-12 es lunes
LUNES_23 = ts(2026, 10, 12, 23)
MARTES_01 = ts(2026, 10, 13, 1)
MARTES_09 = ts(2026, 10, 13, 9)
SABADO_01 = ts(2026, 10, 17, 1)


# --- Catálogo y regex -----------------------------------------------------------------------------------------
def test_regex_de_servicio_cubre_subdominios_y_no_falsos_positivos():
    r = re.compile(control.regex_servicio("tiktok"), re.I)
    assert r.search("www.tiktok.com") and r.search("v16.tiktokcdn.com") and r.search("TIKTOK.COM")
    assert not r.search("nottiktok.com") and not r.search("tiktok.com.evil.org")
    assert control.regex_servicio("youtube").count("googlevideo") == 1
    for sid in control.SERVICIOS:
        re.compile(control.regex_servicio(sid))
        assert control.nombre_grupo(sid).startswith("ARIA-svc-")


def test_sinonimos_de_servicio():
    for t, e in [("TikTok", "tiktok"), ("tik tok", "tiktok"), ("Epic", "fortnite"), ("Fortnite / Epic Games", "fortnite"),
                 ("Disney+", "disneyplus"), ("YouTube", "youtube"), ("twitter", "x"), ("nada", None)]:
        assert control.servicio_id(t) == e


# --- Horarios ------------------------------------------------------------------------------------------------------
def test_horario_que_cruza_la_medianoche():
    h = {"dias": [0, 1, 2, 3, 4], "desde": "23:00", "hasta": "08:00"}
    assert control.horario_activo(h, datetime.fromtimestamp(LUNES_23, tiempo.zona()))
    assert control.horario_activo(h, datetime.fromtimestamp(MARTES_01, tiempo.zona()))
    assert not control.horario_activo(h, datetime.fromtimestamp(MARTES_09, tiempo.zona()))
    # el sábado a la 01:00 es la cola del viernes (día de inicio incluido); el domingo a la 01:00 no (sábado no está)
    assert control.horario_activo(h, datetime.fromtimestamp(SABADO_01, tiempo.zona()))
    assert not control.horario_activo(h, datetime.fromtimestamp(SABADO_01 + 86400, tiempo.zona()))


def test_horario_en_el_mismo_dia():
    h = {"dias": [0], "desde": "16:00", "hasta": "20:00"}
    assert control.horario_activo(h, datetime.fromtimestamp(ts(2026, 10, 12, 16), tiempo.zona()))
    assert not control.horario_activo(h, datetime.fromtimestamp(ts(2026, 10, 12, 20), tiempo.zona()))
    assert not control.horario_activo(h, datetime.fromtimestamp(ts(2026, 10, 13, 17), tiempo.zona()))


def test_validacion_de_horarios(ipad):
    for dias, d, h in [([], "23:00", "08:00"), ([7], "23:00", "08:00"), ([0], "25:00", "08:00"),
                       ([0], "23:00", "23:00"), (["a"], "23:00", "08:00"), ([True], "23:00", "08:00")]:
        with pytest.raises(control.ControlError):
            control.crear_horario(ipad, None, dias, d, h)
    with pytest.raises(control.ControlError):
        control.crear_horario(ipad, "inventado", [0], "10:00", "11:00")


def test_deseado_se_recalcula_desde_los_horarios(ipad):
    control.crear_horario(ipad, None, [0, 1, 2, 3, 4], "23:00", "08:00")
    control.crear_horario(ipad, "tiktok", [0, 1, 2, 3, 4], "16:00", "20:00")
    assert control.calcular_deseado(LUNES_23)[ipad]["pausa"]
    assert not control.calcular_deseado(LUNES_23)[ipad]["servicios"]
    assert control.calcular_deseado(ts(2026, 10, 12, 17))[ipad]["servicios"] == {"tiktok"}
    assert control.calcular_deseado(MARTES_09) == {}


# --- Protecciones --------------------------------------------------------------------------------------------------------
def test_no_se_puede_pausar_router_ni_raspberry_ni_desconocidos():
    router = inventario("AA:00:00:00:00:01", config.ROUTER_IP, "Router")
    pi = inventario("AA:00:00:00:00:02", "192.168.1.50", "Pi")
    fuera = inventario("AA:00:00:00:00:03", "8.8.8.8", "Fuera")
    for clave in (router, pi, fuera, "no-existe", "", None):
        with pytest.raises(control.ControlError):
            control.pausar(clave, 10)
        with pytest.raises(control.ControlError):
            control.bloquear_servicio(clave, "tiktok")
    assert control.calcular_deseado() == {}


def test_protegidas_por_entorno(monkeypatch):
    monkeypatch.setattr(config, "CONTROL_PROTEGIDOS", {"192.168.0.77"})
    x = inventario("AA:00:00:00:00:09", "192.168.0.77", "NAS")
    with pytest.raises(control.ControlError):
        control.pausar(x)


def test_resolver_por_alias_ip_mac_y_parcial(ipad):
    inventario("AA:BB:CC:00:00:02", "192.168.0.51", "Fire TV salón")
    inventario("AA:BB:CC:00:00:03", "192.168.0.52", "Fire TV cuarto")
    assert control.resolver("iPad") == control.resolver("ipad") == control.resolver("el iPad") == ipad
    assert control.resolver("192.168.0.50") == control.resolver("aa:bb:cc:00:00:01") == ipad
    assert control.resolver("fire tv salon") == "AA:BB:CC:00:00:02"      # sin tildes
    with pytest.raises(control.ControlError, match="varios"):
        control.resolver("fire tv")
    with pytest.raises(control.ControlError):
        control.resolver("lavadora")


# --- Reconciliación con Pi-hole falso ----------------------------------------------------------------------------------
def test_pausa_crea_grupo_regla_y_cliente(ph, ipad):
    control.pausar(ipad)
    r = correr(control.reconciliar())
    assert r["ok"] and r["creados"] == 1
    gid = ph.gid(control.GRUPO_PAUSA)
    assert gid != 0
    d = ph.dominios[0]
    assert d["domain"] == ".*" and d["groups"] == [gid] and d["enabled"] and d["comment"].startswith(control.MARCA)
    assert ph.propios() == {"192.168.0.50": sorted([0, gid])}       # conserva Default (anuncios)
    assert ph.clientes[0]["comment"] == control.MARCA + ipad
    # la regla .* se creó desactivada y solo después se activó
    assert ph.escrituras.index(("POST", "/api/domains/deny/regex")) < ph.escrituras.index(("PUT", "/api/domains/deny/regex/.*"))


def test_reconciliar_es_idempotente(ph, ipad):
    control.pausar(ipad)
    control.bloquear_servicio(ipad, "tiktok")
    correr(control.reconciliar())
    ph.escrituras.clear()
    r = correr(control.reconciliar())
    assert r["ok"] and ph.escrituras == []


def test_servicio_y_pausa_se_combinan_y_se_quitan(ph, ipad):
    control.bloquear_servicio(ipad, "TikTok")
    correr(control.reconciliar())
    g_tt = ph.gid("ARIA-svc-tiktok")
    assert ph.propios() == {"192.168.0.50": sorted([0, g_tt])}
    assert ph.dominios[0]["domain"] == control.regex_servicio("tiktok") and ph.dominios[0]["groups"] == [g_tt]
    control.pausar(ipad)
    correr(control.reconciliar())
    assert ph.propios()["192.168.0.50"] == sorted([0, g_tt, ph.gid(control.GRUPO_PAUSA)])
    control.reanudar(ipad)
    control.desbloquear_servicio(ipad, "tiktok")
    r = correr(control.reconciliar())
    assert r["borrados"] == 1 and ph.clientes == []


def test_pausa_con_duracion_caduca(ph, ipad):
    ahora = time.time()
    control.pausar(ipad, 60, ahora)
    correr(control.reconciliar(ahora + 10))
    assert len(ph.clientes) == 1
    r = correr(control.reconciliar(ahora + 3601))
    assert ph.clientes == [] and r["borrados"] == 1
    for m in (0, -5, 10 ** 9, "x", True):
        with pytest.raises(control.ControlError):
            control.pausar(ipad, m)


def test_cambio_de_ip_mueve_el_cliente(ph, ipad):
    control.pausar(ipad)
    correr(control.reconciliar())
    inventario(ipad, "192.168.0.99", "iPad")
    r = correr(control.reconciliar())
    assert r["ok"] and list(ph.propios()) == ["192.168.0.99"]


def test_no_toca_clientes_ni_reglas_ajenos(ph, ipad):
    ph.grupos.append({"name": "Niños", "id": 1, "enabled": True})
    ph.clientes.append({"client": "192.168.0.50", "comment": "a mano", "groups": [0, 1]})
    ph.clientes.append({"client": "192.168.0.60", "comment": "otro", "groups": [0]})
    control.pausar(ipad)
    r = correr(control.reconciliar())
    assert not r["ok"] and "a mano" in r["error"] + "a mano"
    assert {c["client"]: c["comment"] for c in ph.clientes} == {"192.168.0.50": "a mano", "192.168.0.60": "otro"}
    assert ph.clientes[0]["groups"] == [0, 1]
    # sin pausas, tampoco borra lo ajeno
    control.reanudar(ipad)
    correr(control.reconciliar())
    assert len(ph.clientes) == 2


def test_regla_ajena_igual_no_se_modifica(ph, ipad):
    ph.dominios.append({"domain": ".*", "comment": "mía", "enabled": True, "groups": [0], "kind": "regex", "type": "deny"})
    control.pausar(ipad)
    r = correr(control.reconciliar())
    assert not r["ok"] and "ajena" in r["error"]
    assert ph.dominios[0]["groups"] == [0] and ph.clientes == []     # nunca se asigna un cliente sin regla segura


def test_si_pihole_ignora_el_grupo_se_borra_la_regla(ph, ipad):
    """Salvaguarda: una regla .* en Default bloquearía a toda la casa."""
    ph.ignorar_grupos = True
    control.pausar(ipad)
    r = correr(control.reconciliar())
    assert not r["ok"] and ph.dominios == [] and ph.clientes == []


def test_pihole_caido_no_pierde_el_estado_y_reintenta(ph, ipad):
    control.pausar(ipad)
    ph.caido = True
    r = correr(control.reconciliar())
    assert not r["ok"] and r["error"]
    ph.caido = False
    r = correr(control.reconciliar())
    assert r["ok"] and len(ph.clientes) == 1


def test_arranque_limpio_converge(ph, ipad):
    """Tras un reinicio no hay memoria: el estado sale de SQLite y de lo que hay en Pi-hole."""
    control.crear_horario(ipad, None, [0], "23:00", "08:00")
    correr(control.reconciliar(LUNES_23))
    assert len(ph.clientes) == 1
    # queda un cliente propio huérfano de una versión anterior
    ph.clientes.append({"client": "192.168.0.200", "comment": control.MARCA + "ip-192.168.0.200", "groups": [0, 5]})
    correr(control.reconciliar(MARTES_09))
    assert ph.clientes == []


def test_sin_shield_o_desactivado(monkeypatch, ipad):
    monkeypatch.setattr(config, "SHIELD_PASSWORD", "")
    assert not correr(control.reconciliar())["ok"]
    monkeypatch.setattr(config, "CONTROL", False)
    assert "desactivado" in correr(control.reconciliar())["error"]


def test_la_clave_sigue_al_dispositivo_cuando_se_descubre_su_mac(ipad):
    inventario("ip-192.168.0.70", "192.168.0.70", "Switch")
    control.pausar("ip-192.168.0.70")
    control.bloquear_servicio("ip-192.168.0.70", "roblox")
    control.crear_horario("ip-192.168.0.70", None, [0], "10:00", "11:00")
    red._sincronizar([{"ip": "192.168.0.70", "mac": "AA:BB:CC:00:00:70", "nombre": None, "fabricante": None,
                       "clave": "AA:BB:CC:00:00:70"}])
    d = control.calcular_deseado(LUNES_23)
    assert list(d) == ["AA:BB:CC:00:00:70"] and d["AA:BB:CC:00:00:70"]["servicios"] == {"roblox"}
    assert control._horarios()[0]["clave"] == "AA:BB:CC:00:00:70"


# --- Avisos de horario -----------------------------------------------------------------------------------------------------
def test_aviso_cuando_empieza_y_termina_un_horario(ipad, monkeypatch):
    emitidos = []

    async def emitir(tipo, sev, texto, enlace="", *a, **k):
        emitidos.append((tipo, texto))
    monkeypatch.setattr(avisos, "emitir", emitir)
    control.crear_horario(ipad, None, [0], "23:00", "08:00")
    assert correr(control.transiciones(MARTES_09 - 86400 * 2)) == []          # fuera de horario: nada
    assert len(correr(control.transiciones(LUNES_23))) == 1
    assert correr(control.transiciones(LUNES_23 + 60)) == []                  # sin repetir
    assert len(correr(control.transiciones(MARTES_09))) == 1
    assert [t for t, _ in emitidos] == ["control", "control"]
    assert "se queda sin internet" in emitidos[0][1] and "termina" in emitidos[1][1] and "iPad" in emitidos[0][1]


def test_tipo_de_aviso_control_activo_por_defecto_y_solo_admin():
    assert avisos.TIPOS["control"][1] is True and avisos.TIPOS["control"][2] is True
    assert avisos.ajustes_defecto()["tipos"]["control"] is True


# --- Herramientas del agente ---------------------------------------------------------------------------------------------------
@pytest.fixture
def herramientas(ph, monkeypatch):
    async def disp():
        return []
    monkeypatch.setattr(red, "dispositivos", disp)


def test_herramientas_pausar_y_reanudar(herramientas, ph, ipad):
    out = correr(tools.ejecutar("pausar_internet", {"dispositivo": "iPad", "minutos": 60}))
    assert "pausado durante 60 minuto" in out and "DNS" in out
    assert len(ph.clientes) == 1
    assert "pausado" in correr(tools.ejecutar("estado_control", {"dispositivo": "iPad"})) or "sin internet" in \
        correr(tools.ejecutar("estado_control", {"dispositivo": "iPad"}))
    assert "reanudado" in correr(tools.ejecutar("reanudar_internet", {"dispositivo": "ipad"}))
    assert ph.clientes == []


def test_herramientas_servicios(herramientas, ph, ipad):
    assert "TikTok bloqueado" in correr(tools.ejecutar("bloquear_servicio", {"dispositivo": "iPad", "servicio": "tik tok"}))
    assert "Sin TikTok" in correr(tools.ejecutar("estado_control", {})) or "sin TikTok" in correr(tools.ejecutar("estado_control", {}))
    assert "desbloqueado" in correr(tools.ejecutar("desbloquear_servicio", {"dispositivo": "iPad", "servicio": "tiktok"}))
    assert "No conozco" in correr(tools.ejecutar("bloquear_servicio", {"dispositivo": "iPad", "servicio": "xyz"}))
    assert ph.clientes == []


def test_herramientas_rechazan_router_pi_y_minutos_raros(herramientas, ph, monkeypatch):
    monkeypatch.setattr(config, "LAN_IP", "192.168.0.50")  # la Pi se protege por ARIA_LAN_IP
    inventario("AA:00:00:00:00:01", config.ROUTER_IP, "Router")
    inventario("AA:00:00:00:00:02", "192.168.0.50", "Pi")
    for d in ("Router", "192.168.0.50", "Pi"):
        assert "infraestructura" in correr(tools.ejecutar("pausar_internet", {"dispositivo": d, "minutos": 5}))
    assert ph.escrituras == []
    inventario("AA:00:00:00:00:03", "192.168.0.53", "Tablet")
    assert "número" in correr(tools.ejecutar("pausar_internet", {"dispositivo": "Tablet", "minutos": "mucho"}))
    assert "No encuentro" in correr(tools.ejecutar("pausar_internet", {"dispositivo": "todos"}))


def test_herramientas_solo_admin_y_solo_redes(ipad):
    nombres = {"pausar_internet", "reanudar_internet", "bloquear_servicio", "desbloquear_servicio", "estado_control"}
    assert nombres <= tools.permitidas("admin") and not nombres & tools.permitidas("usuario")
    assert "No tienes permiso" in correr(tools.ejecutar("pausar_internet", {"dispositivo": "iPad"}, rol="usuario"))
    from aria import agentes
    assert nombres <= agentes.AGENTES["redes"].herramientas
    assert not nombres & agentes.AGENTES["aria"].herramientas
    assert not nombres & agentes.herramientas(agentes.AGENTES["redes"], "usuario")
    assert nombres <= agentes.herramientas(agentes.AGENTES["redes"], "admin")
    # nada con «todos» ni sin dispositivo
    for n in nombres - {"estado_control"}:
        assert "dispositivo" in tools._REGISTRO[n]["spec"]["function"]["parameters"]["required"]


@pytest.mark.parametrize("frase,esperada", [
    ("pausa el iPad una hora", "pausar_internet"), ("corta el internet de la tablet", "pausar_internet"),
    ("reanuda el wifi del móvil", "reanudar_internet"), ("bloquea tiktok en el móvil", "bloquear_servicio"),
    ("desbloquea youtube", "desbloquear_servicio"), ("qué dispositivos están pausados", "estado_control"),
    ("bloquea fortnite en la switch", "bloquear_servicio")])
def test_intenciones_para_el_cerebro_local(frase, esperada):
    assert esperada in tools.relevantes(frase)


def test_el_bloqueador_de_anuncios_no_dispara_el_control():
    r = tools.relevantes("pausa el bloqueador de anuncios")
    assert "pausar_bloqueador" in r and "pausar_internet" not in r


def test_enrutado_a_redes():
    from aria import agentes
    assert "redes" in agentes.puntuar("pausa el iPad una hora, corta internet", "admin")
    assert "redes" in agentes.puntuar("control parental", "admin")


# --- API (solo admin) --------------------------------------------------------------------------------------------------------------
def cliente_de(u) -> TestClient:
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def test_api_flujo_completo(ph, ipad, admin):
    c = cliente_de(admin)
    h = {"Origin": LAN}
    r = c.post("/api/red/control/pausa", json={"clave": ipad, "minutos": 30}, headers=h)
    assert r.status_code == 200 and r.json()["aplicado"] and len(ph.clientes) == 1
    e = c.get("/api/red/control").json()
    assert e["dispositivos"][0]["pausado"] and e["dispositivos"][0]["pausa_hasta"] and "DNS" in e["limitacion"]
    assert e["servicios"][0]["id"] == "tiktok" and config.ROUTER_IP in e["protegidas"]
    assert c.post("/api/red/control/servicio", json={"clave": ipad, "servicio": "youtube", "bloquear": True}, headers=h).status_code == 200
    r = c.post("/api/red/control/horarios", json={"clave": ipad, "servicio": None, "dias": [0, 1], "desde": "23:00", "hasta": "08:00"}, headers=h)
    hid = r.json()["id"]
    assert c.delete(f"/api/red/control/horarios/{hid}", headers=h).status_code == 200
    assert c.delete(f"/api/red/control/horarios/{hid}", headers=h).status_code == 404
    assert c.post("/api/red/control/reanudar", json={"clave": ipad}, headers=h).json()["estaba_pausado"]
    assert c.post("/api/red/control/servicio", json={"clave": ipad, "servicio": "youtube", "bloquear": False}, headers=h).status_code == 200
    assert ph.clientes == []


def test_api_validaciones(ph, ipad, admin):
    c = cliente_de(admin)
    h = {"Origin": LAN}
    assert c.post("/api/red/control/pausa", json={"clave": "no-existe"}, headers=h).status_code == 400
    assert c.post("/api/red/control/pausa", json={"clave": ipad, "minutos": "5"}, headers=h).status_code == 400
    assert c.post("/api/red/control/pausa", json={}, headers=h).status_code == 400
    assert c.post("/api/red/control/servicio", json={"clave": ipad, "servicio": "x", "bloquear": "si"}, headers=h).status_code == 400
    assert c.post("/api/red/control/horarios", json={"clave": ipad, "dias": [9], "desde": "10:00", "hasta": "11:00"}, headers=h).status_code == 400
    router = inventario("AA:00:00:00:00:01", config.ROUTER_IP, "Router")
    assert c.post("/api/red/control/pausa", json={"clave": router}, headers=h).status_code == 400
    assert ph.escrituras == []


def test_api_guarda_el_estado_aunque_pihole_este_caido(ph, ipad, admin):
    ph.caido = True
    r = cliente_de(admin).post("/api/red/control/pausa", json={"clave": ipad}, headers={"Origin": LAN})
    assert r.status_code == 200 and r.json()["aplicado"] is False and r.json()["aviso"]
    assert control.calcular_deseado()[ipad]["pausa"]


def test_api_rutas_de_control_son_solo_de_admin(ana):
    from aria import api_control, permisos
    c = cliente_de(ana)
    rutas = list(api_control.router.routes)
    assert len(rutas) >= 7
    for r in rutas:
        for m in r.methods - {"HEAD", "OPTIONS"}:
            assert not permisos.permitido("usuario", m, r.path.replace("{hid}", "1")), (m, r.path)
            assert c.request(m, r.path.replace("{hid}", "1"), json={}, headers={"Origin": LAN}).status_code == 403, (m, r.path)


# --- Telegram ---------------------------------------------------------------------------------------------------------------------------
class FalsoBot:
    def __init__(self):
        self.llamadas = []

    async def llamar(self, metodo, espera=20, **d):
        self.llamadas.append((metodo, d))
        return {"message_id": len(self.llamadas)}

    def ultimo(self, metodo="sendMessage"):
        return next(d for m, d in reversed(self.llamadas) if m == metodo)


def _vincular(bot, u, chat_id):
    codigo = tg.crear_codigo(u["id"])["codigo"]
    correr(tg.procesar({"update_id": 1, "message": {"message_id": 1, "chat": {"id": chat_id, "type": "private"},
                                                    "from": {"id": chat_id, "first_name": "Al"}, "text": "/start " + codigo}}, bot))


def _msg(chat_id, texto):
    return {"update_id": 1, "message": {"message_id": 1, "chat": {"id": chat_id, "type": "private"},
                                        "from": {"id": chat_id, "first_name": "Al"}, "text": texto}}


def _pulsar(chat_id, dato):
    return {"update_id": 2, "callback_query": {"id": "cq", "from": {"id": chat_id}, "data": dato,
                                               "message": {"message_id": 9, "chat": {"id": chat_id, "type": "private"}}}}


@pytest.fixture(autouse=False)
def sin_limites(monkeypatch):
    for n in ("_lim_mensajes", "_lim_aviso_rapido", "_lim_desconocido", "_lim_vincular", "_lim_vincular_global"):
        v = getattr(tg, n)
        monkeypatch.setattr(tg, n, avisos.Limitador(v.n, v.ventana))


def test_telegram_control_lista_y_reanuda(ph, ipad, admin, sin_limites):
    bot = FalsoBot()
    _vincular(bot, admin, 100)
    correr(tg.procesar(_msg(100, "/control"), bot))
    assert "Ningún dispositivo" in bot.ultimo()["text"]
    control.pausar(ipad)
    control.bloquear_servicio(ipad, "roblox")
    correr(control.reconciliar())
    correr(tg.procesar(_msg(100, "/control"), bot))
    u = bot.ultimo()
    assert "iPad" in u["text"] and "DNS" in u["text"]
    botones = [b for f in u["reply_markup"]["inline_keyboard"] for b in f]
    assert [b["text"] for b in botones][0].startswith("Reanudar")
    correr(tg.procesar(_pulsar(100, botones[0]["callback_data"]), bot))
    assert control.calcular_deseado().get(ipad, {}).get("pausa") is not True
    assert [c["groups"] for c in ph.clientes] and len(ph.clientes[0]["groups"]) == 2   # queda el servicio, sin la pausa
    correr(tg.procesar(_pulsar(100, botones[0]["callback_data"]), bot))                # ficha de un solo uso
    assert bot.ultimo("answerCallbackQuery")["text"] == "Este botón ya no sirve."
    correr(tg.procesar(_pulsar(100, botones[1]["callback_data"]), bot))
    assert ph.clientes == []


def test_telegram_control_es_de_admin(ana, ph, sin_limites):
    bot = FalsoBot()
    _vincular(bot, ana, 200)
    correr(tg.procesar(_msg(200, "/control"), bot))
    assert "administrador" in bot.ultimo()["text"]
    assert "/control" not in tg._ayuda(False) and "/control" in tg._ayuda(True)


def test_telegram_ficha_de_control_revalida_el_rol(ph, ipad, admin, sin_limites):
    bot = FalsoBot()
    otro = usuarios.crear("bea@example.com", "Bea", "admin", "clave-larga-bea")
    _vincular(bot, otro, 300)
    control.pausar(ipad)
    f = tg.ficha(300, otro["id"], "reanudar_control", {"clave": ipad})
    usuarios.actualizar(otro["id"], rol="usuario")
    correr(tg.procesar(_pulsar(300, f), bot))
    assert control.calcular_deseado()[ipad]["pausa"] and "administrador" in bot.ultimo("answerCallbackQuery")["text"]


def test_dns_privado_bloquea_doh_y_no_el_resto():
    """El «servicio» dns-privado corta los servidores de DNS cifrado (DoT/DoH) sin tocar dominios normales."""
    import re
    rx = re.compile(control.regex_servicio("dns-privado"))
    for d in ("dns.adguard.com", "dns.google", "chrome.cloudflare-dns.com", "one.one.one.one", "mask.icloud.com",
              "dns.quad9.net", "use-application-dns.net"):
        assert rx.search(d), d
    for d in ("google.com", "www.google.com", "adguard.com", "icloud.com", "cloudflare.com", "quad9.net",
              "notdns.google.example"):
        assert not rx.search(d), d
    assert control.servicio_id("dns privado") == "dns-privado" and control.servicio_id("doh") == "dns-privado"
