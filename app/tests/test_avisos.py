"""Motor de avisos: planificador, deduplicación, cooldown, «todo en orden», horas de silencio, chequeos y API."""
import asyncio
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from aria import auth, avisos, avisos_chequeos as ch, main, tiempo, usuarios
from aria.avisos import Chequeo, Problema

LAN = "https://192.168.1.50"


def correr(c):
    return asyncio.run(c)


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


@pytest.fixture
def buzon(monkeypatch):
    """Canal falso: apunta lo que se entregaría."""
    recibidos = []

    async def canal(uid, aviso):
        recibidos.append((uid, aviso))
        return True
    monkeypatch.setattr(avisos, "_CANALES", {"falso": canal})
    monkeypatch.setattr(avisos, "_rachas", {})
    monkeypatch.setattr(avisos, "_ultima_ejecucion", {})
    monkeypatch.setattr(avisos, "en_silencio", lambda a, ref=None: False)
    return recibidos


def mediodia():
    return datetime(2026, 10, 7, 12, 0, tzinfo=tiempo.zona())


# --- Horas de silencio y ajustes -------------------------------------------------------------------------
@pytest.mark.parametrize("h,m,esperado", [(23, 0, True), (2, 30, True), (7, 59, True), (8, 0, False), (12, 0, False),
                                          (22, 59, False)])
def test_silencio_que_cruza_medianoche(h, m, esperado):
    a = avisos.ajustes_defecto()
    assert avisos.en_silencio(a, datetime(2026, 10, 7, h, m, tzinfo=tiempo.zona())) is esperado


def test_silencio_en_el_mismo_dia_y_desactivado():
    a = avisos.normalizar_ajustes({"silencio": {"activo": True, "desde": "14:00", "hasta": "16:00"}})
    assert avisos.en_silencio(a, datetime(2026, 10, 7, 15, 0, tzinfo=tiempo.zona()))
    assert not avisos.en_silencio(a, datetime(2026, 10, 7, 16, 0, tzinfo=tiempo.zona()))
    a["silencio"]["activo"] = False
    assert not avisos.en_silencio(a, datetime(2026, 10, 7, 15, 0, tzinfo=tiempo.zona()))


def test_normalizar_descarta_basura():
    a = avisos.normalizar_ajustes({"tipos": {"copia": False, "inventado": True, "tunel": "sí"},
                                   "silencio": {"desde": "25:00", "hasta": "7:00"}, "briefing": {"canal": "email"},
                                   "voz_telegram": 1, "canales": {"push": False}})
    assert a["tipos"]["copia"] is False and "inventado" not in a["tipos"] and a["tipos"]["tunel"] is True
    assert a["silencio"]["desde"] == "23:00" and a["silencio"]["hasta"] == "08:00"
    assert a["briefing"]["canal"] == "telegram" and a["voz_telegram"] is False and a["canales"]["push"] is False
    assert a["tipos"]["vpn_conexion"] is False  # apagado por defecto


# --- Emitir --------------------------------------------------------------------------------------------------------
def test_avisos_de_admin_solo_a_admins(admin, ana, buzon):
    r = correr(avisos.emitir("copia", "aviso", "copia vieja", "inicio", [admin["id"], ana["id"]]))
    assert [x["uid"] for x in r] == [admin["id"]]
    assert avisos.listar(ana["id"])["avisos"] == []
    # sin destinatarios = todos los administradores activos
    r = correr(avisos.emitir("tunel", "aviso", "túnel caído"))
    assert [x["uid"] for x in r] == [admin["id"]] and buzon[-1][1]["texto"] == "túnel caído"


def test_interruptor_por_tipo(admin, buzon):
    avisos.guardar_ajustes(admin["id"], {"tipos": {"copia": False}})
    assert correr(avisos.emitir("copia", "aviso", "x")) == []
    assert correr(avisos.emitir("tunel", "aviso", "y"))[0]["canales"] == ["falso"]


def test_horas_de_silencio_guardan_pero_no_entregan_salvo_grave(admin, buzon, monkeypatch):
    monkeypatch.setattr(avisos, "en_silencio", lambda a, ref=None: True)
    r = correr(avisos.emitir("tunel", "aviso", "de noche"))
    assert r[0]["silencio"] and r[0]["canales"] == [] and buzon == []
    assert avisos.listar(admin["id"])["avisos"][0]["entregado_por"] == ["web"]
    r = correr(avisos.emitir("servicios", "grave", "DNS caído"))
    assert r[0]["canales"] == ["falso"]
    r = correr(avisos.emitir("recordatorio", "aviso", "pastilla", "", [admin["id"]], ignorar_silencio=True))
    assert r[0]["canales"] == ["falso"]


def test_canal_que_falla_no_rompe(admin, monkeypatch):
    async def roto(uid, aviso):
        raise RuntimeError("caído")

    async def bueno(uid, aviso):
        return True
    monkeypatch.setattr(avisos, "_CANALES", {"roto": roto, "bueno": bueno})
    monkeypatch.setattr(avisos, "en_silencio", lambda a, ref=None: False)
    assert correr(avisos.emitir("tunel", "aviso", "x"))[0]["canales"] == ["bueno"]


def test_campana_api_e_idor(admin, ana, buzon):
    correr(avisos.emitir("prueba", "info", "para ana", "", [ana["id"]]))
    correr(avisos.emitir("tunel", "aviso", "para admin"))
    ca, cadm = cliente_de(ana), cliente_de(admin)
    d = ca.get("/api/avisos").json()
    assert d["no_leidos"] == 1 and d["avisos"][0]["texto"] == "para ana"
    aid_admin = cadm.get("/api/avisos").json()["avisos"][0]["id"]
    assert ca.post(f"/api/avisos/{aid_admin}/leido").status_code == 404
    assert cadm.get("/api/avisos").json()["no_leidos"] == 1
    assert ca.post(f"/api/avisos/{d['avisos'][0]['id']}/leido").status_code == 200
    assert ca.get("/api/avisos").json()["no_leidos"] == 0
    assert cadm.post("/api/avisos/leidos").json()["marcados"] == 1


def test_ajustes_api_tipos_por_rol(admin, ana):
    ca = cliente_de(ana)
    d = ca.get("/api/avisos/ajustes").json()
    assert [t["id"] for t in d["tipos"]] == ["agenda"] and d["telegram"]["configurado"] is False and d["push"]["clave"]
    assert len(cliente_de(admin).get("/api/avisos/ajustes").json()["tipos"]) == len(avisos.TIPOS)
    r = ca.post("/api/avisos/ajustes", json={"silencio": {"activo": False}, "voz_telegram": True})
    assert r.json()["ajustes"]["voz_telegram"] is True
    assert avisos.ajustes(ana["id"])["silencio"]["activo"] is False
    assert avisos.ajustes(admin["id"])["silencio"]["activo"] is True


def test_probar_avisos_con_limite(ana, buzon):
    c = cliente_de(ana)
    assert c.post("/api/avisos/probar").json()["canales"] == ["falso"]
    for _ in range(3):
        r = c.post("/api/avisos/probar")
    assert r.status_code == 429


# --- Deduplicación, confirmaciones, cooldown y «todo en orden» -------------------------------------------------------
def _cheq(estado, **kw):
    async def fn():
        return estado["problemas"]
    return Chequeo(kw.pop("id", "prueba"), kw.pop("tipo", "tunel"), "aviso", fn, **kw)


def test_dedupe_y_todo_en_orden(admin, buzon):
    e = {"problemas": [Problema("caido", "Está caído")]}
    c = _cheq(e, texto_ok="Vuelve a funcionar")
    assert correr(avisos.ejecutar_chequeo(c, 1000)) == ["Está caído"]
    assert correr(avisos.ejecutar_chequeo(c, 1060)) == []  # sigue caído: no se repite
    e["problemas"] = []
    assert correr(avisos.ejecutar_chequeo(c, 1120)) == ["Vuelve a funcionar"]
    assert correr(avisos.ejecutar_chequeo(c, 1180)) == []
    assert [a["texto"] for a in reversed(avisos.listar(admin["id"])["avisos"])] == ["Está caído", "Vuelve a funcionar"]


def test_confirmaciones_evitan_falsos_positivos(admin, buzon):
    e = {"problemas": [Problema("caido", "Caído")]}
    c = _cheq(e, confirmaciones=3, texto_ok="OK")
    assert correr(avisos.ejecutar_chequeo(c, 0)) == []
    assert correr(avisos.ejecutar_chequeo(c, 60)) == []
    e["problemas"] = []  # se recupera antes de confirmar: ni aviso ni «todo en orden»
    assert correr(avisos.ejecutar_chequeo(c, 120)) == []
    e["problemas"] = [Problema("caido", "Caído")]
    for t in (180, 240):
        assert correr(avisos.ejecutar_chequeo(c, t)) == []
    assert correr(avisos.ejecutar_chequeo(c, 300)) == ["Caído"]


def test_cooldown_entre_avisos_de_la_misma_clave(admin, buzon):
    e = {"problemas": [Problema("k", "Problema")]}
    c = _cheq(e, cooldown_s=600, texto_ok="Arreglado")
    assert correr(avisos.ejecutar_chequeo(c, 0)) == ["Problema"]
    e["problemas"] = []
    assert correr(avisos.ejecutar_chequeo(c, 60)) == ["Arreglado"]
    e["problemas"] = [Problema("k", "Problema")]
    assert correr(avisos.ejecutar_chequeo(c, 120)) == []  # dentro del cooldown: se calla...
    e["problemas"] = []
    assert correr(avisos.ejecutar_chequeo(c, 180)) == []  # ...y tampoco hay «todo en orden»
    e["problemas"] = [Problema("k", "Problema")]
    assert correr(avisos.ejecutar_chequeo(c, 700)) == ["Problema"]


def test_repetir_mientras_siga(admin, buzon):
    e = {"problemas": [Problema("k", "Sigue mal")]}
    c = _cheq(e, repetir_s=3600)
    assert correr(avisos.ejecutar_chequeo(c, 0)) == ["Sigue mal"]
    assert correr(avisos.ejecutar_chequeo(c, 1800)) == []
    assert correr(avisos.ejecutar_chequeo(c, 3700)) == ["Sigue mal"]


def test_evento_con_linea_base(admin, buzon):
    e = {"problemas": [Problema("aa", "viejo")]}
    c = _cheq(e, id="disp", tipo="dispositivo_nuevo", evento=True, linea_base=True)
    assert correr(avisos.ejecutar_chequeo(c, 0)) == []  # primera pasada: lo que ya había no se avisa
    e["problemas"] = [Problema("aa", "viejo"), Problema("bb", "nuevo")]
    assert correr(avisos.ejecutar_chequeo(c, 60)) == ["nuevo"]
    assert correr(avisos.ejecutar_chequeo(c, 120)) == []  # cada clave, una sola vez
    e["problemas"] = []
    assert correr(avisos.ejecutar_chequeo(c, 180)) == []  # los eventos no tienen «todo en orden»


def test_chequeo_sin_datos_no_cambia_nada(admin, buzon):
    e = {"problemas": [Problema("k", "x")]}
    c = _cheq(e, texto_ok="ok")
    correr(avisos.ejecutar_chequeo(c, 0))
    e["problemas"] = None
    assert correr(avisos.ejecutar_chequeo(c, 60)) == []


def test_tipo_apagado_por_defecto_no_se_comprueba(admin, buzon):
    llamado = []

    async def fn():
        llamado.append(1)
        return [Problema("1", "móvil conectado")]
    c = Chequeo("vpn_conexion", "vpn_conexion", "info", fn)
    assert correr(avisos.ejecutar_chequeo(c, 0)) == [] and llamado == []
    avisos.guardar_ajustes(admin["id"], {"tipos": {"vpn_conexion": True}})
    correr(avisos.ejecutar_chequeo(c, 60))
    assert llamado == [1]


def test_tick_respeta_intervalos(admin, buzon, monkeypatch):
    llamadas = []

    async def fn():
        llamadas.append(1)
        return []
    monkeypatch.setattr(avisos, "_CHEQUEOS", {"x": Chequeo("x", "tunel", "aviso", fn, intervalo_s=300)})

    async def nada(*a, **k):
        return []
    from aria import recordatorios
    monkeypatch.setattr(recordatorios, "disparar_vencidos", nada)
    monkeypatch.setattr(avisos, "briefings_programados", nada)
    for t in (1000, 1100, 1200, 1300):
        correr(avisos.tick(t))
    assert len(llamadas) == 2


def test_chequeo_que_explota_no_para_el_tick(admin, buzon, monkeypatch):
    async def mal():
        raise RuntimeError("boom")
    ok = []

    async def bien():
        ok.append(1)
        return []
    monkeypatch.setattr(avisos, "_CHEQUEOS", {"a": Chequeo("a", "tunel", "aviso", mal), "b": Chequeo("b", "tunel", "aviso", bien)})

    async def nada(*a, **k):
        return []
    from aria import recordatorios
    monkeypatch.setattr(recordatorios, "disparar_vencidos", nada)
    monkeypatch.setattr(avisos, "briefings_programados", nada)
    correr(avisos.tick(5000))
    assert ok == [1]


# --- Chequeos concretos con datos falsos ------------------------------------------------------------------------------
def _servicios(monkeypatch, dns=True, web=True, vpn=True):
    async def estado():
        return {"shield_dns": {"dns_ok": dns, "web_ok": web}, "heimdall": {"web_ok": vpn}}
    monkeypatch.setattr(ch.services, "estado", estado)


def test_chequeo_shield_y_heimdall(monkeypatch):
    _servicios(monkeypatch)
    assert correr(ch.shield_dns()) == [] and correr(ch.heimdall()) == []
    _servicios(monkeypatch, dns=False)
    assert correr(ch.shield_dns())[0].clave == "dns"
    _servicios(monkeypatch, dns=False, web=False, vpn=False)
    assert correr(ch.shield_dns())[0].clave == "caido" and correr(ch.heimdall())[0].clave == "caido"


@pytest.mark.parametrize("estado,caido", [(302, False), (200, False), (530, True), (502, True), (403, True)])
def test_chequeo_tunel(monkeypatch, estado, caido):
    monkeypatch.setattr(ch.config, "URL_PUBLICA", "https://aria.ejemplo.com")
    real = httpx.AsyncClient
    monkeypatch.setattr(ch.httpx, "AsyncClient",
                        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(estado)), **kw))
    assert bool(correr(ch.tunel())) is caido


def test_chequeo_tunel_sin_conexion_y_sin_url(monkeypatch):
    monkeypatch.setattr(ch.config, "URL_PUBLICA", "")
    assert correr(ch.tunel()) is None
    monkeypatch.setattr(ch.config, "URL_PUBLICA", "https://aria.ejemplo.com")
    real = httpx.AsyncClient

    def falla(r):
        raise httpx.ConnectError("no")
    monkeypatch.setattr(ch.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(falla), **kw))
    assert "ConnectError" in correr(ch.tunel())[0].texto


def test_chequeo_dispositivos_nuevos(monkeypatch):
    from aria import red, shield
    monkeypatch.setattr(shield, "configurado", lambda: False)
    assert correr(ch.dispositivos_nuevos()) is None
    monkeypatch.setattr(shield, "configurado", lambda: True)

    async def ds():
        return [{"clave": "AA", "ip": "192.168.0.50", "nombre": "tele", "conocido": True},
                {"clave": "BB", "ip": "192.168.0.66", "fabricante": "Xiaomi", "conocido": False}]
    monkeypatch.setattr(red, "dispositivos", ds)
    p = correr(ch.dispositivos_nuevos())
    assert [x.clave for x in p] == ["BB"] and "Xiaomi" in p[0].texto and "192.168.0.66" in p[0].texto


def test_chequeo_hallazgos_graves(monkeypatch):
    from aria import escaneo, seguridad
    monkeypatch.setattr(ch, "_ultimo_escaneo", {"id": None})
    monkeypatch.setattr(escaneo, "ultimo", lambda: {"id": "e1", "hosts": []})
    monkeypatch.setattr(escaneo, "anterior_a", lambda rid: None)
    monkeypatch.setattr(seguridad, "hallazgos_de_escaneo", lambda res, ant, inv: [
        {"gravedad": "alta", "tipo": "telnet", "titulo": "Telnet abierto", "ip": "192.168.0.9", "recomendacion": "Ciérralo."},
        {"gravedad": "media", "tipo": "http", "titulo": "Panel web", "ip": "192.168.0.1", "recomendacion": ""}])
    p = correr(ch.hallazgos_graves())
    assert len(p) == 1 and "Telnet" in p[0].texto
    assert correr(ch.hallazgos_graves()) == []  # mismo escaneo: no se recalcula
    monkeypatch.setattr(escaneo, "ultimo", lambda: None)
    assert correr(ch.hallazgos_graves()) is None


def test_chequeo_copia(monkeypatch):
    from aria import briefing
    monkeypatch.setattr(briefing, "ultima_copia", lambda: {"disponible": False})
    assert correr(ch.copia()) is None
    monkeypatch.setattr(briefing, "ultima_copia", lambda: {"disponible": True, "hace": "hace 2 d", "antigua": True})
    assert "hace 2 d" in correr(ch.copia())[0].texto
    monkeypatch.setattr(briefing, "ultima_copia", lambda: {"disponible": True, "hace": "hace 3 h", "antigua": False})
    assert correr(ch.copia()) == []


def test_chequeos_de_sistema(monkeypatch):
    monkeypatch.setattr(ch.sistema, "temperatura", lambda: 80.2)
    monkeypatch.setattr(ch.sistema, "disco", lambda: {"porcentaje": 91.0})
    monkeypatch.setattr(ch.sistema, "memoria", lambda: {"total": 100, "disponible": 3})
    assert "80,2" in correr(ch.temperatura())[0].texto
    assert "91,0" in correr(ch.disco())[0].texto
    assert correr(ch.ram())[0].clave == "baja"
    monkeypatch.setattr(ch.sistema, "temperatura", lambda: 55.0)
    monkeypatch.setattr(ch.sistema, "disco", lambda: {"porcentaje": 40.0})
    monkeypatch.setattr(ch.sistema, "memoria", lambda: {"total": 100, "disponible": 60})
    assert correr(ch.temperatura()) == correr(ch.disco()) == correr(ch.ram()) == []
    monkeypatch.setattr(ch.sistema, "temperatura", lambda: None)
    assert correr(ch.temperatura()) is None


def test_chequeo_vpn(monkeypatch):
    monkeypatch.setattr(ch.vpn, "configurado", lambda: True)

    async def lista():
        return [{"id": 1, "nombre": "movil", "conectado": True}, {"id": 2, "nombre": "portatil", "conectado": False}]
    monkeypatch.setattr(ch.vpn, "listar", lista)
    p = correr(ch.vpn_conexiones())
    assert [x.clave for x in p] == ["1"] and "movil" in p[0].texto


def test_vpn_avisa_solo_de_conexiones_nuevas(admin, buzon):
    avisos.guardar_ajustes(admin["id"], {"tipos": {"vpn_conexion": True}})
    e = {"problemas": [Problema("1", "movil conectado")]}
    c = _cheq(e, id="vpn_conexion", tipo="vpn_conexion", linea_base=True, cooldown_s=0)
    assert correr(avisos.ejecutar_chequeo(c, 0)) == []        # ya estaba conectado al arrancar
    e["problemas"] = [Problema("1", "movil conectado"), Problema("2", "portatil conectado")]
    assert correr(avisos.ejecutar_chequeo(c, 60)) == ["portatil conectado"]
    e["problemas"] = [Problema("2", "portatil conectado")]
    assert correr(avisos.ejecutar_chequeo(c, 120)) == []       # desconexión: en silencio
    e["problemas"] = [Problema("1", "movil conectado"), Problema("2", "portatil conectado")]
    assert correr(avisos.ejecutar_chequeo(c, 180)) == ["movil conectado"]


def test_chequeo_cerebros(monkeypatch):
    from aria import cerebros

    class P:
        def __init__(s, i, nube):
            s.id, s.nube = i, nube

        def tiene_clave(s):
            return True
    monkeypatch.setattr(cerebros, "PROVEEDORES", {"groq": P("groq", True), "local": P("local", False)})
    monkeypatch.setattr(cerebros, "configuracion", lambda: (["groq", "local"], set()))
    monkeypatch.setattr(cerebros, "hay_nube", lambda: True)
    assert correr(ch.cerebros_caidos()) == []
    monkeypatch.setattr(cerebros, "hay_nube", lambda: False)
    assert correr(ch.cerebros_caidos())[0].clave == "solo_local"
    monkeypatch.setattr(cerebros, "configuracion", lambda: (["groq", "local"], {"groq"}))
    assert correr(ch.cerebros_caidos()) is None  # sin nube configurada no hay nada que avisar


def test_cerebros_avisa_tras_30_minutos(admin, buzon):
    e = {"problemas": [Problema("solo_local", "solo local")]}
    c = _cheq(e, id="cerebros", tipo="cerebros", confirmaciones=30)
    emitidos = [correr(avisos.ejecutar_chequeo(c, i * 60)) for i in range(30)]
    assert emitidos[-1] == ["solo local"] and not any(emitidos[:-1])


def test_registrar_chequeos():
    ch.registrar()
    ids = set(avisos.chequeos())
    assert {"shield_dns", "heimdall", "tunel", "dispositivo_nuevo", "seguridad", "copia", "temperatura", "disco", "ram",
            "vpn_conexion", "cerebros"} <= ids
    assert all(c.tipo in avisos.TIPOS for c in avisos.chequeos().values())


# --- Resumen de buenos días programado -----------------------------------------------------------------------------------
def test_briefing_ventana():
    a = avisos.ajustes_defecto()
    z = tiempo.zona()
    assert not avisos.briefing_toca(a, datetime(2026, 10, 7, 7, 59, tzinfo=z))
    assert avisos.briefing_toca(a, datetime(2026, 10, 7, 8, 0, tzinfo=z))
    assert avisos.briefing_toca(a, datetime(2026, 10, 7, 10, 30, tzinfo=z))
    assert not avisos.briefing_toca(a, datetime(2026, 10, 7, 11, 5, tzinfo=z))
    a["briefing"]["activo"] = False
    assert not avisos.briefing_toca(a, datetime(2026, 10, 7, 8, 30, tzinfo=z))


def test_briefing_programado_una_vez_al_dia(admin, monkeypatch):
    from aria import briefing
    enviados = []

    async def tg(uid, aviso):
        enviados.append((uid, aviso["tipo"], aviso["texto"]))
        return True
    monkeypatch.setattr(avisos, "_CANALES", {"telegram": tg})

    async def obtener(u, refrescar=False, ref=None):
        return {"x": 1}
    monkeypatch.setattr(briefing, "obtener", obtener)
    monkeypatch.setattr(briefing, "texto_hablado", lambda d: "Buenos días, Lucía.")
    ref = datetime(2026, 10, 7, 8, 5, tzinfo=tiempo.zona())
    assert correr(avisos.briefings_programados(ref)) == [admin["id"]]
    assert correr(avisos.briefings_programados(ref)) == []
    assert enviados == [(admin["id"], "resumen", "Buenos días, Lucía.")]
    assert avisos.listar(admin["id"])["avisos"] == []  # no ensucia la campana


def test_purgar(admin, buzon):
    correr(avisos.emitir("tunel", "aviso", "viejo"))
    assert avisos.purgar(dias=-1) == 1
