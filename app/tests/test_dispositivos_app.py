"""Tokens de lectura para dispositivos nativos."""
import time
from contextlib import closing
from datetime import datetime

from fastapi.testclient import TestClient
import pytest

from aria import api_app, auth, avisos, dispositivos_app, invitados, main, usuarios

LAN = "https://192.168.1.50"


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


def cliente(u) -> TestClient:
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def anonimo() -> TestClient:
    return TestClient(main.app, base_url=LAN, follow_redirects=False)


def _sin_red(monkeypatch, contador: list | None = None) -> None:
    """Limitador del resumen nuevo (aislado del resto de pruebas) y tiempo sin salir a internet."""
    monkeypatch.setattr(api_app, "_lim_resumen", avisos.Limitador(60, 3600))

    async def tiempo(_):
        if contador is not None:
            contador.append(1)
        return {"ciudad": "Villarriba de Arriba", "actual": 21, "min": 12, "max": 27, "cielo": "despejado"}

    monkeypatch.setattr(main.briefing, "_tiempo", tiempo)


async def _casa_falsa():
    return {"anuncios": 1234, "porcentaje": 12.5, "bloqueo_activo": True, "vpn_conectados": 1, "servicios_ok": True}


def test_resumen_trae_tres_proximos_y_casa_solo_para_admin(admin, monkeypatch):
    _sin_red(monkeypatch)
    monkeypatch.setattr(api_app, "_casa", _casa_falsa)
    ahora = datetime(2026, 10, 17, 10, 0, tzinfo=main.briefing.tiempo.zona())
    monkeypatch.setattr(main.briefing.tiempo, "ahora", lambda: ahora)
    eventos = [{"titulo": f"Evento {i}", "inicio": f"2026-10-{18 + i}T10:00:00+02:00"} for i in range(5)]
    monkeypatch.setattr(main.agenda, "listar_eventos", lambda *_: eventos)
    r = anonimo().get("/api/app/resumen", headers={"Authorization": "Bearer " + dispositivos_app.crear(admin["id"], "Pixel")["token"]})
    d = r.json()
    assert [e["titulo"] for e in d["proximos"]] == ["Evento 0", "Evento 1", "Evento 2"]
    assert d["proximo"]["titulo"] == "Evento 0" and d["casa"]["anuncios"] == 1234
    ana = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    r = anonimo().get("/api/app/resumen", headers={"Authorization": "Bearer " + dispositivos_app.crear(ana["id"], "Móvil")["token"]})
    assert r.json()["casa"] is None   # el estado de la red solo lo ve quien la administra


def test_casa_aguanta_que_falle_un_servicio(monkeypatch):
    import asyncio
    async def falla():
        raise RuntimeError("SHIELD-DNS caído")
    async def servicios():
        return {"shield_dns": {"estado": "ok"}, "heimdall": {"estado": "no_instalado"}}
    monkeypatch.setattr(api_app.shield, "configurado", lambda: True)
    monkeypatch.setattr(api_app.shield, "resumen", falla)
    monkeypatch.setattr(api_app.vpn, "configurado", lambda: False)
    monkeypatch.setattr(api_app.services, "estado", servicios)
    casa = asyncio.run(api_app._casa())
    assert casa["anuncios"] is None and casa["vpn_conectados"] is None and casa["servicios_ok"] is False


def test_token_solo_se_devuelve_al_crear_y_se_guarda_su_huella(admin):
    dispositivos_app.iniciar()
    r = dispositivos_app.crear(admin["id"], "Pixel")
    assert r["token"].startswith("ariad_")
    with dispositivos_app.db._con() as con:
        fila = con.execute("SELECT * FROM app_dispositivos").fetchone()
    assert fila["huella"] not in r["token"]
    assert dispositivos_app.verificar(r["token"])["id"] == admin["id"]


def test_bearer_solo_abre_el_resumen(admin, monkeypatch):
    token = dispositivos_app.crear(admin["id"], "Móvil")["token"]

    async def tiempo(_):
        return {"ciudad": "Casa", "actual": 20, "min": 10, "max": 25, "cielo": "despejado"}

    monkeypatch.setattr(main.briefing, "_tiempo", tiempo)
    monkeypatch.setattr(api_app, "_casa", _casa_falsa)
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    r = c.get("/api/app/resumen", headers={"Authorization": "Bearer " + token})
    assert r.status_code == 200
    assert set(r.json()) == {"avisos", "tiempo", "proximo", "proximos", "casa", "hogar", "generado"}
    assert c.get("/api/avisos", headers={"Authorization": "Bearer " + token}).status_code in (303, 401)


def test_resumen_en_texto_para_siri(admin, monkeypatch):
    _sin_red(monkeypatch)
    token = dispositivos_app.crear(admin["id"], "Atajos de iPhone")["token"]
    ahora = datetime(2026, 10, 17, 10, 0, tzinfo=main.briefing.tiempo.zona())
    monkeypatch.setattr(main.briefing.tiempo, "ahora", lambda: ahora)
    monkeypatch.setattr(main.avisos, "listar", lambda _uid, _limite: {"avisos": [
        {"id": 1, "texto": "Revisar la copia de seguridad antes de salir.", "severidad": "aviso", "creado": 1, "leido": False}
    ]})
    monkeypatch.setattr(main.agenda, "listar_eventos", lambda *_: [{"titulo": "Dentista", "inicio": "2026-10-18T17:30:00+02:00"}])
    r = anonimo().get("/api/app/resumen?formato=texto", headers={"Authorization": "Bearer " + token})
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; charset=utf-8"
    assert r.text == "Tienes 1 aviso sin leer: Revisar la copia de seguridad antes de salir. En Villarriba de Arriba hace 21 grados, despejado; máxima de 27. Tu próximo evento: Dentista, mañana a las 17:30."


def test_resumen_en_texto_vacio_dice_todo_tranquilo(admin, monkeypatch):
    _sin_red(monkeypatch)
    token = dispositivos_app.crear(admin["id"], "Atajos de iPhone")["token"]
    monkeypatch.setattr(main.avisos, "listar", lambda _uid, _limite: {"avisos": []})
    async def sin_tiempo(*_):
        return None
    monkeypatch.setattr(main.briefing, "_tiempo", sin_tiempo)   # es asíncrona: el doble también
    monkeypatch.setattr(main.agenda, "listar_eventos", lambda *_: [])
    r = anonimo().get("/api/app/resumen?formato=texto", headers={"Authorization": "Bearer " + token})
    assert r.status_code == 200
    assert r.text == "Todo tranquilo: no tienes avisos."


def test_maximo_diez_y_revocacion(admin):
    tokens = [dispositivos_app.crear(admin["id"], str(i))["token"] for i in range(11)]
    assert len(dispositivos_app.listar(admin["id"])) == 10
    assert dispositivos_app.verificar(tokens[0]) is None
    ultimo = dispositivos_app.listar(admin["id"])[0]["id"]
    assert dispositivos_app.revocar(admin["id"], ultimo)


# --- Bearer ----------------------------------------------------------------------------------------------------------
def test_bearer_invalidos_caducado_revocado_y_cuenta_baja_dan_401(admin, monkeypatch):
    _sin_red(monkeypatch)
    c = anonimo()
    token = dispositivos_app.crear(admin["id"], "Pixel")["token"]
    assert c.get("/api/app/resumen").status_code == 401
    formatos_raros = [
        "Bearer",                                     # esquema sin token
        "bearer " + token,                            # esquema en minúsculas
        "Bearer  " + token,                           # doble espacio
        "Bearer " + token[:-1],                       # un carácter menos
        "Bearer ariad_" + "A" * 43,                   # bien formado pero jamás emitido
        "Basic " + token,                             # otro esquema
        "Bearer " + token + " ",                      # sobra un espacio final
    ]
    for cabecera in formatos_raros:
        assert c.get("/api/app/resumen", headers={"Authorization": cabecera}).status_code == 401, cabecera
    # Caducado: la fecha de caducidad, en el pasado (SQL directa sobre su ficha)
    vencido = dispositivos_app.crear(admin["id"], "Vencido")
    with closing(dispositivos_app.db._con()) as con, con:
        con.execute("UPDATE app_dispositivos SET caduca=? WHERE id=?", (time.time() - 1, vencido["id"]))
    assert c.get("/api/app/resumen", headers={"Authorization": "Bearer " + vencido["token"]}).status_code == 401
    # Revocado desde la web con sesión: el token deja de servir al instante
    revocado = dispositivos_app.crear(admin["id"], "Revocado")
    assert cliente(admin).delete(f"/api/app/dispositivos/{revocado['id']}",
                                 headers={"Origin": LAN}).status_code == 200
    assert c.get("/api/app/resumen", headers={"Authorization": "Bearer " + revocado["token"]}).status_code == 401
    # Cuenta desactivada: su ficha sigue en la tabla, pero el usuario ya no vale
    baja = usuarios.crear("baja@example.com", "Baja", "usuario", "clave-baja-larga")
    token_baja = dispositivos_app.crear(baja["id"], "Tablet")["token"]
    assert c.get("/api/app/resumen", headers={"Authorization": "Bearer " + token_baja}).status_code == 200
    usuarios.actualizar(baja["id"], activo=False)
    assert c.get("/api/app/resumen", headers={"Authorization": "Bearer " + token_baja}).status_code == 401


def test_resumen_con_bearer_no_toca_cookies_y_no_se_cachea(admin, monkeypatch):
    _sin_red(monkeypatch)
    token = dispositivos_app.crear(admin["id"], "Pixel")["token"]
    c = anonimo()
    r = c.get("/api/app/resumen", headers={"Authorization": "Bearer " + token})
    assert r.status_code == 200
    assert not any(cabecera.lower() == "set-cookie" for cabecera in r.headers)
    assert r.headers["cache-control"] == "no-store"
    assert c.cookies.get(auth.COOKIE) is None


def test_el_bearer_no_abre_otras_rutas(admin):
    token = dispositivos_app.crear(admin["id"], "Pixel")["token"]
    c = anonimo()
    for ruta in ("/api/avisos", "/api/info", "/api/app/dispositivos"):
        r = c.get(ruta, headers={"Authorization": "Bearer " + token})
        assert r.status_code != 200, ruta
        assert c.cookies.get(auth.COOKIE) is None


def test_solo_se_abre_get_api_app_resumen(admin):
    token = dispositivos_app.crear(admin["id"], "Pixel")["token"]
    c = anonimo()
    cabecera = {"Authorization": "Bearer " + token}
    assert c.get("/api/app/resumen/", headers=cabecera).status_code != 200      # barra final
    assert c.get("/api/app/resumenX", headers=cabecera).status_code != 200      # ruta parecida
    assert c.post("/api/app/resumen", headers=cabecera).status_code != 200      # método incorrecto


def test_ni_un_invitado_ni_el_admin_en_vista_pueden_crear_token(admin, monkeypatch):
    monkeypatch.setattr(api_app, "_lim_crear", avisos.Limitador(5, 3600))
    s = invitados.solicitar("Nora", "nora@example.com", "Vengo a ver la casa", "203.0.113.44")
    invitada = invitados.aprobar(s["id"], "visita")["usuario"]
    r = cliente(invitada).post("/api/app/dispositivos", json={"nombre": "Móvil de Nora"}, headers={"Origin": LAN})
    assert r.status_code == 403
    # El mismo admin, pero «probando el perfil Visita» con la cookie de vista
    c = cliente(admin)
    c.cookies.set(main.VISTA_COOKIE, "visita")
    r = c.post("/api/app/dispositivos", json={"nombre": "Móvil de la jefa"}, headers={"Origin": LAN})
    assert r.status_code == 403
    # y ya sin la vista, sí puede vincular
    c.cookies.delete(main.VISTA_COOKIE)
    r = c.post("/api/app/dispositivos", json={"nombre": "Móvil de la jefa"}, headers={"Origin": LAN})
    assert r.status_code == 200 and r.json()["token"].startswith("ariad_")


def test_resumen_de_un_invitado_sin_inicio_ni_agenda(monkeypatch):
    llamadas: list = []
    _sin_red(monkeypatch, llamadas)
    s = invitados.solicitar("Nora", "nora@example.com", "Vengo a ver la casa", "203.0.113.44")
    invitada = invitados.aprobar(s["id"], "visita", limites={"secciones": ["chat"]})["usuario"]
    token = dispositivos_app.crear(invitada["id"], "Móvil de Nora")["token"]
    # normalizar_limites reinserta «inicio» en cada lectura; aquí se fija el acceso del invitado
    # (sin Inicio ni Agenda) para comprobar qué decide el resumen con esos límites.
    de_real = invitados.de

    def acceso_sin_inicio(uid):
        lim = de_real(uid)
        if lim is None:
            return None
        return {**lim, "secciones": [s_ for s_ in lim["secciones"] if s_ not in ("inicio", "agenda")]}

    monkeypatch.setattr(invitados, "de", acceso_sin_inicio)
    r = anonimo().get("/api/app/resumen", headers={"Authorization": "Bearer " + token})
    assert r.status_code == 200
    d = r.json()
    assert d["tiempo"] is None and d["proximo"] is None
    assert llamadas == []


def test_la_peticion_61_del_resumen_en_la_hora_dan_429(admin, monkeypatch):
    _sin_red(monkeypatch)
    token = dispositivos_app.crear(admin["id"], "Pixel")["token"]
    c = anonimo()
    cabecera = {"Authorization": "Bearer " + token}
    for i in range(60):
        assert c.get("/api/app/resumen", headers=cabecera).status_code == 200, i
    assert c.get("/api/app/resumen", headers=cabecera).status_code == 429


def test_no_se_revoca_el_dispositivo_ajeno_y_la_lista_no_enseña_secretos():
    duena = usuarios.crear("marta@example.com", "Marta", "usuario", "clave-marta-larga")
    propio = dispositivos_app.crear(duena["id"], "Móvil de Marta")
    ajeno = usuarios.crear("hugo@example.com", "Hugo", "usuario", "clave-hugo-larga")
    c = cliente(ajeno)
    assert c.delete(f"/api/app/dispositivos/{propio['id']}", headers={"Origin": LAN}).status_code == 404
    assert dispositivos_app.verificar(propio["token"])["id"] == duena["id"]
    assert c.get("/api/app/dispositivos").json()["dispositivos"] == []
    for lista in (c.get("/api/app/dispositivos").json()["dispositivos"],
                  cliente(duena).get("/api/app/dispositivos").json()["dispositivos"],
                  cliente(usuarios.por_identificador("admin")).get("/api/app/dispositivos").json()["dispositivos"]):
        for d in lista:
            assert "token" not in d and "huella" not in d
    assert len(cliente(duena).get("/api/app/dispositivos").json()["dispositivos"]) == 1


def test_verificar_anota_el_ultimo_uso(admin):
    """El UPDATE de ultimo_uso debe confirmarse (antes se perdía al cerrar la conexión)."""
    from contextlib import closing
    from aria import db, dispositivos_app
    creado = dispositivos_app.crear(admin["id"], "Móvil de prueba")
    assert dispositivos_app.verificar(creado["token"])["id"] == admin["id"]
    with closing(db._con()) as con:
        fila = con.execute("SELECT ultimo_uso FROM app_dispositivos WHERE id=?", (creado["id"],)).fetchone()
    assert fila["ultimo_uso"] is not None


def test_casa_da_direcciones_locales_y_el_certificado_raiz(admin, monkeypatch, tmp_path):
    from aria import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "LAN_IP", "192.168.1.50")
    monkeypatch.setattr(config, "HOSTS", {"192.168.1.50", "aria.local", "aria.ejemplo.com", "127.0.0.1", "mal host.local"})
    assert cliente(admin).get("/api/app/casa").status_code == 404   # sin certificado no hay plan B
    (tmp_path / "aria-certificado.crt").write_text("-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n")
    d = cliente(admin).get("/api/app/casa").json()
    assert d["direcciones"] == ["https://192.168.1.50/", "https://aria.local/"]   # la IP primero; nada público
    assert d["certificado"].startswith("-----BEGIN CERTIFICATE-----")
    assert anonimo().get("/api/app/casa").status_code in (303, 401)



def test_resumen_trae_hogar_con_lo_ya_conocido(admin, monkeypatch):
    from aria import hogar_cache
    _sin_red(monkeypatch)
    monkeypatch.setattr(api_app, "_casa", _casa_falsa)
    hogar_cache.limpiar()
    hogar_cache._datos["camaras"] = (0, [{"privacidad": True, "en_linea": True}, {"privacidad": False, "en_linea": False}])
    hogar_cache._datos["luces"] = (0, [{"encendida": True}, {"encendida": False}])
    token = dispositivos_app.crear(admin["id"], "Pixel")["token"]
    h = anonimo().get("/api/app/resumen", headers={"Authorization": "Bearer " + token}).json()["hogar"]
    assert h["camaras"] == 2 and h["tapadas"] == 1 and h["sin_respuesta"] == 1 and h["luces_encendidas"] == 1
    hogar_cache.limpiar()
