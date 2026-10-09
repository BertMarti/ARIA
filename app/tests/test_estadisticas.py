"""Estadísticas por dispositivo de Pi-hole, informe semanal y comando /informe de Telegram.

Pi-hole y la Bot API son FALSOS (httpx.MockTransport): nada de red. Cubre la unión con el inventario
de red, el cálculo del % de bloqueo, la caché de 60 s, el error legible con SHIELD-DNS caído, los
permisos de las rutas nuevas, el informe con y sin servicios, la deduplicación semanal persistente
(tras un reinicio simulado) y que /informe es solo de administradores."""
import asyncio
import time
from contextlib import closing
from datetime import datetime
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient

from aria import (agentes, auth, avisos, briefing, config, db, estadisticas, main, permisos, red,
                  shield, telegram as tg, tiempo, tools, usuarios, vpn)

LAN = "https://192.168.1.50"
PORTATIL = "AA:BB:CC:00:00:01"
CONSOLA = "AA:BB:CC:00:00:02"
IP_PORTATIL = "192.168.1.61"
IP_CONSOLA = "192.168.1.62"
IP_SIN_NOMBRE = "192.168.1.99"


class FalsoPihole:
    """API v6 mínima para estadísticas: auth, history (memoria y BD), top_clients, top_domains y queries.

    `actual` es la semana en curso y `anterior` la previa; se distinguen por el parámetro `from` que
    Pi-hole recibe en los endpoints históricos."""

    def __init__(self):
        self.actual = {"clients": [], "bloqueados": [], "dominios": [],
                       "total_queries": 0, "blocked_queries": 0}
        self.anterior = dict(self.actual)
        self.historial = []
        self.consultas = []
        self.peticiones = []
        self.caido = False

    def handler(self, req: httpx.Request) -> httpx.Response:
        if self.caido:
            raise httpx.ConnectError("caído")
        ruta, m = unquote(req.url.path), req.method
        self.peticiones.append(ruta)
        if ruta == "/api/auth":
            return httpx.Response(200, json={"session": {"sid": "sid-falso"}}) if m == "POST" else httpx.Response(204)
        if req.headers.get("X-FTL-SID") != "sid-falso":
            return httpx.Response(401, json={})
        if m != "GET":
            return httpx.Response(404, json={})
        if ruta in ("/api/history/clients", "/api/history/database/clients"):
            return httpx.Response(200, json={"clients": {}, "history": self.historial})
        bloqueado = req.url.params.get("blocked") == "true"
        d = self._datos(req)
        if ruta in ("/api/stats/top_clients", "/api/stats/database/top_clients"):
            return httpx.Response(200, json={"clients": d["bloqueados"] if bloqueado else d["clients"],
                                             "total_queries": d["total_queries"],
                                             "blocked_queries": d["blocked_queries"]})
        if ruta in ("/api/stats/top_domains", "/api/stats/database/top_domains"):
            return httpx.Response(200, json={"domains": d["dominios"] if bloqueado else []})
        if ruta == "/api/queries":
            ip = req.url.params.get("client_ip")
            return httpx.Response(200, json={"queries": [q for q in self.consultas
                                                         if (q.get("client") or {}).get("ip") == ip],
                                             "cursor": None})
        return httpx.Response(404, json={})

    def _datos(self, req) -> dict:
        desde = req.url.params.get("from")
        if desde and int(desde) < time.time() - 10 * 86400:
            return self.anterior          # ventana de la semana previa (desde hace más de 10 días)
        return self.actual


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
    monkeypatch.setattr(shield, "_sid", "sid-falso")   # sesión ya abierta: esto no prueba la autenticación
    return f


@pytest.fixture(autouse=True)
def cache_limpia():
    """La caché de estadísticas vive en el módulo: se vacía antes y después de cada prueba."""
    estadisticas._CACHE.clear()
    yield
    estadisticas._CACHE.clear()


@pytest.fixture(autouse=True)
def limites(monkeypatch):
    for n in ("_lim_mensajes", "_lim_aviso_rapido", "_lim_desconocido", "_lim_vincular", "_lim_vincular_global"):
        v = getattr(tg, n)
        monkeypatch.setattr(tg, n, avisos.Limitador(v.n, v.ventana))


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def inventario(clave, ip, nombre=None, alias=None, conocido=1, primera_vez=1.0, ultima_vez=None):
    with closing(db._con()) as con, con:
        con.execute("INSERT OR REPLACE INTO red_inventario "
                    "(clave, mac, ip, nombre, alias, conocido, primera_vez, ultima_vez) VALUES (?,?,?,?,?,?,?,?)",
                    (clave, None if clave.startswith("ip-") else clave, ip, nombre, alias,
                     conocido, primera_vez, ultima_vez or primera_vez))
    return clave


def correr(c):
    return asyncio.run(c)


def cliente_de(u) -> TestClient:
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


@pytest.fixture
def datos(ph):
    """Pi-hole con dos dispositivos del inventario y uno desconocido, serie de 24 h y consultas."""
    ahora = time.time()
    inventario(PORTATIL, IP_PORTATIL, nombre="Portátil salón")
    inventario(CONSOLA, IP_CONSOLA, alias="Consola")
    ph.actual = {
        "clients": [{"ip": IP_PORTATIL, "name": "portatil.lan", "count": 200},
                    {"ip": IP_CONSOLA, "name": "consola.lan", "count": 100},
                    {"ip": IP_SIN_NOMBRE, "name": "nadie.lan", "count": 50}],
        "bloqueados": [{"ip": IP_PORTATIL, "count": 60},
                       {"ip": IP_CONSOLA, "count": 40},
                       {"ip": IP_SIN_NOMBRE, "count": 20}],
        "dominios": [{"domain": "anuncios.ejemplo.com", "count": 512},
                     {"domain": "rastreo.ejemplo.net", "count": 260}],
        "total_queries": 400,
        "blocked_queries": 120,
    }
    ph.anterior = {
        "clients": [{"ip": IP_PORTATIL, "count": 180}],
        "bloqueados": [{"ip": IP_PORTATIL, "count": 50}],
        "dominios": [],
        "total_queries": 300,
        "blocked_queries": 90,
    }
    ph.historial = [
        {"timestamp": ahora - 3600 * 30, "data": {IP_PORTATIL: 999}},        # fuera de las 24 h
        {"timestamp": ahora - 3600 * 2, "data": {IP_PORTATIL: 40, IP_CONSOLA: 10}},
        {"timestamp": ahora - 3600, "data": {IP_PORTATIL: 30, IP_CONSOLA: 5, IP_SIN_NOMBRE: 7}},
    ]
    ph.consultas = [
        {"domain": "anuncios.ejemplo.com", "status": "GRAVITY", "client": {"ip": IP_PORTATIL}},
        {"domain": "anuncios.ejemplo.com", "status": "DENYLIST", "client": {"ip": IP_PORTATIL}},
        {"domain": "malware.ejemplo.net", "status": "REGEX", "client": {"ip": IP_PORTATIL}},
        {"domain": "sospechoso.ejemplo.com", "status": "EXTERNAL_BLOCKED_3rd_party", "client": {"ip": IP_PORTATIL}},
        {"domain": "correo.ejemplo.com", "status": "FORWARDED", "client": {"ip": IP_PORTATIL}},
        {"domain": "video.ejemplo.com", "status": "CACHE", "client": {"ip": IP_PORTATIL}},
        {"domain": "mapas.ejemplo.com", "status": "GRAVITY", "client": {"ip": IP_CONSOLA}},
    ]
    return ph


@pytest.fixture
def informe_listo(monkeypatch):
    """Copia de seguridad y HEIMDALL sin depender del entorno real."""
    monkeypatch.setattr(briefing, "ultima_copia", lambda: {"disponible": False})

    async def sin_vpn():
        raise vpn.VpnError("HEIMDALL no está conectado.")
    monkeypatch.setattr(vpn, "listar", sin_vpn)


@pytest.fixture
def sin_servicios(informe_listo, monkeypatch):
    """Ni SHIELD-DNS ni HEIMDALL disponibles."""
    monkeypatch.setattr(config, "SHIELD_PASSWORD", "")


async def _vpn_conectados():
    reciente = datetime.fromtimestamp(time.time() - 3600, tz=tiempo.zona()).isoformat()
    return [{"nombre": "Móvil", "ultimo_handshake": reciente, "recibido": 5 * 1024 ** 2, "enviado": 2 * 1024 ** 2},
            {"nombre": "Portátil viejo", "ultimo_handshake": "2020-01-01T00:00:00+00:00",
             "recibido": 1024, "enviado": 1024}]


# --- Estadísticas por dispositivo ---------------------------------------------------------------------------------
def test_resumen_une_el_inventario_y_calcula_el_porcentaje(datos):
    d = correr(estadisticas.resumen(24))
    assert d["horas"] == 24
    por_ip = {x["ip"]: x for x in d["dispositivos"]}
    p = por_ip[IP_PORTATIL]
    assert (p["nombre"], p["clave"]) == ("Portátil salón", PORTATIL)
    assert (p["consultas"], p["bloqueadas"], p["porcentaje"]) == (200, 60, 30.0)
    assert (por_ip[IP_CONSOLA]["nombre"], por_ip[IP_CONSOLA]["porcentaje"]) == ("Consola", 40.0)
    # Sin fila en el inventario se queda con la IP como nombre y la clave ip-…
    assert (por_ip[IP_SIN_NOMBRE]["nombre"], por_ip[IP_SIN_NOMBRE]["clave"]) == (IP_SIN_NOMBRE, f"ip-{IP_SIN_NOMBRE}")
    assert por_ip[IP_SIN_NOMBRE]["porcentaje"] == 40.0
    assert [x["ip"] for x in d["dispositivos"]] == [IP_PORTATIL, IP_CONSOLA, IP_SIN_NOMBRE]  # por consultas
    assert d["totales"] == {"consultas": 400, "bloqueadas": 120, "porcentaje": 30.0}


def test_serie_temporal_y_ventana_de_siete_dias(datos):
    d = correr(estadisticas.resumen(24))
    p = next(x for x in d["dispositivos"] if x["ip"] == IP_PORTATIL)
    assert [pt["consultas"] for pt in p["serie"]] == [40, 30]      # el punto de hace 30 h no cuenta en 24 h
    assert all(pt["ts"] % 3600 == 0 for pt in p["serie"])
    desconocido = next(x for x in d["dispositivos"] if x["ip"] == IP_SIN_NOMBRE)
    assert [pt["consultas"] for pt in desconocido["serie"]] == [7]
    # 7 días: mismos datos pero por los endpoints históricos de Pi-hole
    semana = correr(estadisticas.resumen(168))
    assert semana["horas"] == 168 and semana["totales"]["consultas"] == 400
    assert semana["dispositivos"][0]["nombre"] == "Portátil salón"
    rutas = set(datos.peticiones)
    assert {"/api/history/clients", "/api/history/database/clients",
            "/api/stats/top_clients", "/api/stats/database/top_clients"} <= rutas


def test_caché_de_un_minuto(datos):
    assert estadisticas._CACHE_S == 60
    a = correr(estadisticas.resumen(24))
    llamadas = len(datos.peticiones)
    b = correr(estadisticas.resumen(24))
    assert b is a and len(datos.peticiones) == llamadas        # dentro del minuto no se vuelve a preguntar
    # Pasan 61 s: la entrada caduca y se consulta a Pi-hole otra vez
    momento, valor = estadisticas._CACHE[("resumen", 24)]
    estadisticas._CACHE[("resumen", 24)] = (momento - 61, valor)
    c = correr(estadisticas.resumen(24))
    assert c is not a and len(datos.peticiones) > llamadas and c["totales"] == a["totales"]


def test_pihole_caido_da_error_legible(datos, admin):
    datos.caido = True
    with pytest.raises(estadisticas.EstadisticasError) as e:
        correr(estadisticas.resumen(24))
    assert "SHIELD-DNS" in str(e.value) and "contactar" in str(e.value)
    r = cliente_de(admin).get("/api/red/estadisticas")
    assert r.status_code == 200 and r.json()["disponible"] is False and "contactar" in r.json()["error"]
    # Y en el detalle el mensaje es el mismo, con la misma respuesta legible
    with pytest.raises(estadisticas.EstadisticasError, match="SHIELD-DNS"):
        correr(estadisticas.detalle(PORTATIL))


def test_validaciones_y_dispositivo_desconocido(datos, admin):
    c = cliente_de(admin)
    r = c.get("/api/red/estadisticas?horas=25")
    assert r.status_code == 400 and "24 o 168" in r.json()["error"]
    assert c.get(f"/api/red/estadisticas/{PORTATIL}").status_code == 200
    r = c.get("/api/red/estadisticas/no-existe")
    assert r.status_code == 404 and "no encontrado" in r.json()["error"]
    assert c.get("/api/red/estadisticas").status_code == 200


def test_detalle_con_los_top10(datos):
    d = correr(estadisticas.detalle(PORTATIL))
    assert (d["clave"], d["nombre"], d["ip"]) == (PORTATIL, "Portátil salón", IP_PORTATIL)
    assert d["serie"], "el detalle lleva la serie del resumen"
    assert [(x["dominio"], x["veces"]) for x in d["bloqueados"]] == [
        ("anuncios.ejemplo.com", 2), ("malware.ejemplo.net", 1), ("sospechoso.ejemplo.com", 1)]
    assert [(x["dominio"], x["veces"]) for x in d["permitidos"]] == [
        ("correo.ejemplo.com", 1), ("video.ejemplo.com", 1)]
    # ip-… funciona aunque el dispositivo no esté en el inventario (aquí no tiene consultas)
    otro = correr(estadisticas.detalle(f"ip-{IP_SIN_NOMBRE}"))
    assert (otro["nombre"], otro["ip"]) == (IP_SIN_NOMBRE, IP_SIN_NOMBRE)
    assert otro["bloqueados"] == [] and [pt["consultas"] for pt in otro["serie"]] == [7]


def test_rutas_de_estadisticas_y_del_informe_son_de_admin(datos, admin, ana, informe_listo):
    h = {"Origin": LAN}
    c = cliente_de(admin)
    assert c.get("/api/red/estadisticas").status_code == 200
    assert c.get(f"/api/red/estadisticas/{PORTATIL}").status_code == 200
    r = c.post("/api/avisos/informe-semanal/probar", headers=h)
    assert r.status_code == 200 and "canales" in r.json()
    assert any(a["tipo"] == "informe_semanal" for a in avisos.listar(admin["id"])["avisos"])
    u = cliente_de(ana)
    for metodo, ruta in (("GET", "/api/red/estadisticas"),
                         ("GET", f"/api/red/estadisticas/{PORTATIL}"),
                         ("POST", "/api/avisos/informe-semanal/probar")):
        assert not permisos.permitido("usuario", metodo, ruta), ruta
        assert u.request(metodo, ruta, json={}, headers=h).status_code == 403, ruta
    assert permisos.permitido("admin", "GET", "/api/red/estadisticas")


def test_herramienta_estadisticas_dispositivo(datos, monkeypatch):
    async def sin_escaneo():
        return []
    monkeypatch.setattr(red, "dispositivos", sin_escaneo)
    # Se resuelve por alias/nombre, por IP y por MAC
    portatil = "Portátil salón (192.168.1.61): dominios bloqueados: anuncios.ejemplo.com (2)"
    for texto, esperado in (("Portátil salón", portatil), ("Consola", "Consola (192.168.1.62): "
                                                                  "dominios bloqueados: mapas.ejemplo.com (1)"),
                            (IP_PORTATIL, portatil), ("aa:bb:cc:00:00:01", portatil)):
        out = correr(tools.ejecutar("estadisticas_dispositivo", {"dispositivo": texto}))
        assert esperado in out, texto
    resumen_txt = correr(tools.ejecutar("estadisticas_dispositivo", {}))
    assert "En las últimas 24 horas: 400 consultas, 120 bloqueadas (30.0 %)" in resumen_txt
    assert "Portátil salón: 200 consultas" in resumen_txt
    assert "No encuentro" in correr(tools.ejecutar("estadisticas_dispositivo", {"dispositivo": "inventado"}))
    assert "No tienes permiso" in correr(tools.ejecutar("estadisticas_dispositivo", {}, rol="usuario"))


def test_herramienta_solo_de_administradores_y_del_agente_redes():
    assert "estadisticas_dispositivo" in tools.permitidas("admin")
    assert "estadisticas_dispositivo" not in tools.permitidas("usuario")
    assert "estadisticas_dispositivo" not in tools.SOLO_LECTURA
    assert "estadisticas_dispositivo" in agentes.AGENTES["redes"].herramientas
    assert "estadisticas_dispositivo" not in agentes.AGENTES["aria"].herramientas
    assert "estadisticas_dispositivo" not in agentes.herramientas(agentes.AGENTES["redes"], "usuario")
    assert "estadisticas_dispositivo" in agentes.herramientas(agentes.AGENTES["redes"], "admin")


@pytest.mark.parametrize("frase", ["¿cuánto navega el portátil?", "qué bloquea la consola",
                                   "muéstrame las estadísticas de la red", "qué consulta el televisor"])
def test_intenciones_de_estadisticas(frase):
    assert "estadisticas_dispositivo" in tools.relevantes(frase)
    assert "redes" in agentes.puntuar(frase, "admin")


# --- Informe semanal ------------------------------------------------------------------------------------------------
def test_informe_semanal_con_todos_los_servicios(datos, admin, monkeypatch, informe_listo):
    inventario("AA:BB:CC:00:00:05", "192.168.1.70", nombre="Dispositivo nuevo", primera_vez=time.time() - 86400)
    inventario(f"ip-{IP_SIN_NOMBRE}", IP_SIN_NOMBRE, nombre=None, conocido=0)
    monkeypatch.setattr(vpn, "listar", _vpn_conectados)
    monkeypatch.setattr(briefing, "ultima_copia", lambda: {"disponible": True, "hace": "hace 2 días"})
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO avisos (user_id, tipo, severidad, texto, enlace, creado) VALUES (?,?,?,?,?,?)",
                    (admin["id"], "sistema", "grave", "Disco al 92 %", "sistema", time.time()))
    texto = correr(estadisticas.construir_informe_semanal())
    assert texto.startswith("📊 **Informe semanal de ARIA**")
    for seccion in ("**Bloqueador**", "**VPN (HEIMDALL)**", "**Red**", "**Sistema**"):
        assert seccion in texto, seccion
    assert "400 consultas, 120 bloqueadas (30.0 %)" in texto
    assert "Semana anterior: 300 consultas (33.3 % de cambio)" in texto
    assert "Portátil salón (200), Consola (100)" in texto
    assert "anuncios.ejemplo.com (512), rastreo.ejemplo.net (260)" in texto
    assert "Móvil (7.0 MB)" in texto and "Portátil viejo" not in texto
    assert "Nuevos esta semana: Dispositivo nuevo" in texto
    assert "Sin nombre: 192.168.1.99" in texto
    assert "Última copia: hace 2 días" in texto
    assert "Avisos graves: Disco al 92 %" in texto


def test_informe_semanal_sin_servicios(sin_servicios):
    """Cada sección se omite con elegancia: solo queda la cabecera, sin errores."""
    texto = correr(estadisticas.construir_informe_semanal())
    assert texto == "📊 **Informe semanal de ARIA**"


def test_informe_programado_se_envia_una_sola_vez_por_semana(admin, monkeypatch, sin_servicios):
    recibidos = []

    async def canal(uid, aviso):
        recibidos.append((uid, aviso["tipo"], aviso["texto"]))
        return True
    monkeypatch.setattr(avisos, "_CANALES", {"telegram": canal})
    domingo = datetime(2026, 10, 11, 20, 5, tzinfo=tiempo.zona())      # domingo a las 20:05
    assert correr(avisos.informes_semanales_programados(domingo)) == [admin["id"]]
    assert [(uid, tipo) for uid, tipo, _ in recibidos] == [(admin["id"], "informe_semanal")]
    assert "Informe semanal" in recibidos[0][2]
    assert correr(avisos.informes_semanales_programados(domingo)) == []            # no se repite en la misma semana
    # «Reinicio»: se vacía la memoria en caliente; la deduplicación vive en SQLite
    estadisticas._CACHE.clear()
    shield._sid = None
    avisos._rachas.clear()
    avisos._ultima_ejecucion.clear()
    avisos.iniciar()
    assert correr(avisos.informes_semanales_programados(domingo)) == []
    assert len(recibidos) == 1
    assert [a["tipo"] for a in avisos.listar(admin["id"])["avisos"]] == ["informe_semanal"]
    # La semana siguiente vuelve a salir
    assert correr(avisos.informes_semanales_programados(domingo.replace(day=18))) == [admin["id"]]
    assert len(recibidos) == 2


def test_los_ajustes_del_informe_se_guardan_en_el_servidor(admin):
    guardado = avisos.guardar_ajustes(admin["id"],
                                      {"informe": {"activo": True, "dia": 6, "hora": "20:00", "canal": "telegram"}})
    assert guardado["informe"] == {"activo": True, "dia": 6, "hora": "20:00", "canal": "telegram"}
    assert avisos.ajustes(admin["id"])["informe"]["hora"] == "20:00"


# --- Telegram --------------------------------------------------------------------------------------------------------
class FalsoBot:
    def __init__(self):
        self.llamadas = []

    async def llamar(self, metodo, espera=20, **d):
        self.llamadas.append((metodo, d))
        if metodo == "getMe":
            return {"id": 1, "username": "aria_bot_falso"}
        return {"message_id": len(self.llamadas)}

    def textos(self):
        return [d.get("text") for m, d in self.llamadas if m == "sendMessage"]

    def ultimo(self, metodo="sendMessage"):
        return next(d for m, d in reversed(self.llamadas) if m == metodo)


@pytest.fixture
def bot():
    return FalsoBot()


def msg(chat_id, texto, tipo="private"):
    return {"update_id": 1, "message": {"message_id": 1, "chat": {"id": chat_id, "type": tipo},
                                        "from": {"id": chat_id, "first_name": "Al"}, "text": texto}}


def vincular(bot, u, chat_id):
    c = tg.crear_codigo(u["id"])
    correr(tg.procesar(msg(chat_id, f"/start {c['codigo']}"), bot))
    assert tg.chat_vinculado(chat_id)["user_id"] == u["id"]


def test_comando_informe_solo_para_administradores(bot, admin, ana, sin_servicios):
    vincular(bot, ana, 200)
    correr(tg.procesar(msg(200, "/informe"), bot))
    assert "administrador" in bot.textos()[-1]
    vincular(bot, admin, 100)
    correr(tg.procesar(msg(100, "/informe"), bot))
    t = bot.textos()[-1]
    assert "Informe semanal" in t and "administrador" not in t
    assert "/informe" in tg._ayuda(True)
    assert ("informe", "Informe semanal (admin)") in tg.COMANDOS


def test_la_ayuda_no_lista_informe_a_los_usuarios():
    assert "/informe" not in tg._ayuda(False)


def test_informe_se_registra_en_los_comandos_del_bot(bot, monkeypatch):
    monkeypatch.setattr(tg, "_yo", {})
    assert correr(tg.preparar(bot))
    cmds = {c["command"] for c in bot.ultimo("setMyCommands")["commands"]}
    assert "informe" in cmds
