import time

import pytest
from fastapi.testclient import TestClient

from aria import api_acceso, auth, cf_access, config, invitados, main, telegram, usuarios

LAN = "https://192.168.1.50"


def anonimo():
    return TestClient(main.app, base_url=LAN, follow_redirects=False)


def cliente(u):
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def _pedir(email="lucia@example.com", ip="203.0.113.7", nombre="Lucía"):
    return invitados.solicitar(nombre, email, "Soy amiga de la casa", ip)


def _invitada(perfil="visita"):
    s = _pedir()
    return invitados.aprobar(s["id"], perfil)["usuario"]


# --- Solicitudes ------------------------------------------------------------------------------------------------------
def test_solicitud_valida_y_sus_errores():
    with pytest.raises(invitados.AccesoError, match="nombre"):
        invitados.solicitar("", "a@example.com", "Hola, soy yo", "1.1.1.1")
    with pytest.raises(invitados.AccesoError, match="email"):
        invitados.solicitar("Ana", "no-es-email", "Hola, soy yo", "1.1.1.1")
    with pytest.raises(invitados.AccesoError, match="frase"):
        invitados.solicitar("Ana", "a@example.com", "hey", "1.1.1.1")
    r = invitados.solicitar("<b>Ana</b>", "A@Example.com", "Soy la vecina", "1.1.1.1")
    s = invitados.solicitud(r["id"])
    assert s["estado"] == "pendiente" and s["email"] == "a@example.com" and "<" not in s["nombre"]
    assert invitados.estado_publico(r["token"]) == {"estado": "pendiente", "nombre": s["nombre"]}
    assert invitados.estado_publico("x") is None


def test_misma_persona_no_duplica_y_hay_limite_por_ip():
    a = _pedir()
    b = _pedir()
    assert b["repetida"] and b["token"] is None and a["token"]   # el token solo lo tiene quien la envió
    _pedir("otro@example.com")
    with pytest.raises(invitados.AccesoError, match="mañana"):
        _pedir("tercero@example.com")
        _pedir("cuarto@example.com")


def test_tope_de_pendientes(monkeypatch):
    monkeypatch.setattr(invitados, "MAX_PENDIENTES", 2)
    _pedir("a@example.com", "10.0.0.1")
    _pedir("b@example.com", "10.0.0.2")
    with pytest.raises(invitados.AccesoError, match="muchas"):
        _pedir("c@example.com", "10.0.0.3")


def test_la_ip_se_guarda_como_huella():
    _pedir(ip="198.51.100.9")
    from contextlib import closing
    from aria import db
    with closing(db._con()) as con:
        ip = con.execute("SELECT ip FROM solicitudes_acceso").fetchone()[0]
    assert ip != "198.51.100.9" and len(ip) == 24


def test_aprobar_crea_usuario_sin_contrasena_y_con_limites():
    s = _pedir()
    u = invitados.aprobar(s["id"])["usuario"]
    assert u["rol"] == "usuario" and u["activo"] and not u["tiene_password"]
    lim = invitados.de(u["id"])
    assert lim["perfil"] == "visita" and lim["mensajes_dia"] == 20 and lim["voz"] == "local"
    assert 6.9 * 86400 < lim["caduca"] - time.time() <= 7 * 86400
    with pytest.raises(invitados.AccesoError, match="aprobada"):
        invitados.aprobar(s["id"])


def test_rechazar_y_no_tocar_a_un_admin():
    s = _pedir()
    assert invitados.rechazar(s["id"])["estado"] == "rechazada"
    admin = usuarios.crear("jefa@example.com", "Jefa", "admin")
    s2 = invitados.solicitar("Jefa", admin["email"], "Quiero entrar", "9.9.9.9")
    with pytest.raises(invitados.AccesoError, match="administrador"):
        invitados.aprobar(s2["id"])


# --- Límites ----------------------------------------------------------------------------------------------------------
def test_rutas_de_una_visita():
    lim = invitados.normalizar_limites(None, "visita")
    si = ["/api/chat", "/api/conversations", "/api/informacion/noticias", "/api/mapa/buscar", "/api/resumen-diario",
          "/api/resumen-diario/voz", "/api/voz/hablar", "/api/avisos", "/api/info", "/"]
    no = ["/api/finanzas/resumen", "/api/agenda", "/api/shield", "/api/system", "/api/vpn/clients", "/api/memoria",
          "/api/telegram/vincular", "/api/rutinas", "/api/briefing", "/api/modulos", "/api/red/salud", "/api/acceso"]
    assert all(invitados.permitido(lim, r) for r in si)
    assert not any(invitados.permitido(lim, r) for r in no)
    assert invitados.permitido(None, "/api/finanzas/resumen")   # sin límites: lo decide solo el rol


def test_familiar_y_personalizado():
    fam = invitados.normalizar_limites(None, "familiar")
    assert invitados.permitido(fam, "/api/finanzas/resumen") and invitados.permitido(fam, "/api/memoria")
    p = invitados.normalizar_limites({"secciones": ["chat", "inventada"], "voz": "no", "mensajes_dia": -3, "memoria": "sí"}, "visita")
    assert p["secciones"] == ["inicio", "chat"] and p["voz"] == "no" and p["mensajes_dia"] == 20 and p["memoria"] is False
    assert not invitados.permitido(p, "/api/voz/hablar")


def test_herramientas_sin_datos_de_casa():
    h = invitados.herramientas(invitados.normalizar_limites(None, "visita"))
    assert {"tiempo", "noticias", "mapa_ir", "buscar_en_internet"} <= h
    assert not h & {"estado_bloqueador", "dispositivos_vpn", "estado_sistema", "estado_servicios", "resumen_diario",
                     "recordar", "crear_evento", "resumen_mes"}
    fam = invitados.herramientas(invitados.normalizar_limites(None, "familiar"))
    assert {"recordar", "crear_evento", "resumen_mes"} <= fam and "estado_bloqueador" not in fam


def test_cupo_diario():
    u = _invitada()
    lim = invitados.de(u["id"])
    for _ in range(20):
        invitados.gastar(u["id"], lim)
    with pytest.raises(invitados.AccesoError, match="20 mensajes"):
        invitados.gastar(u["id"], lim)
    with pytest.raises(invitados.AccesoError, match="imágenes"):
        invitados.gastar(u["id"], lim, "imagenes")
    assert invitados.gastar(1, None) is None


# --- HTTP -------------------------------------------------------------------------------------------------------------
def test_pagina_y_solicitud_publicas(monkeypatch):
    avisos = []

    async def avisar(sid):
        avisos.append(sid)
    monkeypatch.setattr(telegram, "avisar_solicitud", avisar)
    c = anonimo()
    assert c.get("/acceso").status_code == 200 and "Entrar en ARIA" in c.get("/acceso").text
    assert c.get("/static/acceso/acceso.js").status_code == 200
    assert c.get("/acceso/config").json() == {"turnstile": None}
    r = c.post("/acceso/solicitar", json={"nombre": "Lucía", "email": "lucia@example.com", "motivo": "Soy amiga de la casa"})
    assert r.status_code == 200 and r.json()["token"]
    assert c.get("/acceso/estado/" + r.json()["token"]).json()["estado"] == "pendiente"
    assert c.get("/acceso/estado/" + "x" * 24).status_code == 404
    trampa = c.post("/acceso/solicitar", json={"nombre": "Bot", "email": "bot@example.com", "motivo": "spam spam", "web": "http://x"})
    assert trampa.json() == {"ok": True, "token": None} and len(invitados.pendientes()) == 1
    assert c.get("/api/acceso").status_code == 401


def test_turnstile_obligatorio_si_esta_configurado(monkeypatch):
    monkeypatch.setattr(config, "TURNSTILE_SECRETO", "secreto")

    async def falla(respuesta, ip):
        return False
    monkeypatch.setattr(api_acceso, "_turnstile_ok", falla)
    r = anonimo().post("/acceso/solicitar", json={"nombre": "Lucía", "email": "l@example.com", "motivo": "Soy amiga"})
    assert r.status_code == 400 and not invitados.pendientes()


def test_la_gestion_es_solo_de_administradores():
    u = usuarios.crear("normal@example.com", "Normal", "usuario")
    assert cliente(u).get("/api/acceso").status_code == 403
    admin = usuarios.crear("jefa@example.com", "Jefa", "admin")
    d = cliente(admin).get("/api/acceso").json()
    assert d["pendientes"] == [] and "visita" in d["perfiles"] and d["cloudflare"] is False


def test_aprobar_desde_la_web_y_revocar(monkeypatch):
    admin = usuarios.crear("jefa@example.com", "Jefa", "admin")
    s = _pedir()
    c = cliente(admin)
    r = c.post(f"/api/acceso/solicitudes/{s['id']}/aprobar", json={"perfil": "familiar"})
    assert r.status_code == 200 and r.json()["cloudflare"] == "manual"
    uid = r.json()["usuario"]["id"]
    assert invitados.de(uid)["perfil"] == "familiar" and invitados.de(uid)["caduca"] is None
    r = c.patch(f"/api/acceso/invitados/{uid}", json={"perfil": "visita", "dias": 3})
    assert r.json()["limites"]["perfil"] == "visita"
    assert c.post(f"/api/acceso/invitados/{uid}/revocar").status_code == 200
    assert not usuarios.por_id(uid)["activo"]
    r = c.patch(f"/api/acceso/invitados/{uid}", json={"dias": 7, "reactivar": True})
    assert usuarios.por_id(uid)["activo"]


def test_el_middleware_aplica_los_limites(monkeypatch):
    u = _invitada()
    c = cliente(u)
    info = c.get("/api/info").json()
    assert info["limites"]["perfil"] == "visita" and "finanzas" not in info["limites"]["secciones"]
    assert c.get("/api/finanzas/resumen").status_code == 403
    assert c.get("/api/agenda").status_code == 403
    assert c.get("/api/shield").status_code == 403
    assert c.get("/api/informacion/temas").status_code == 200
    invitados.fijar(u["id"], "visita", dias=0)
    from contextlib import closing
    from aria import db
    with closing(db._con()) as con, con:
        con.execute("UPDATE invitados SET caduca=? WHERE user_id=?", (time.time() - 5, u["id"]))
    invitados.olvidar_cache()
    r = c.get("/api/informacion/temas")
    assert r.status_code == 403 and "caducado" in r.json()["error"]


def test_chat_con_cupo_agotado(monkeypatch):
    u = _invitada()
    lim = invitados.de(u["id"])
    for _ in range(lim["mensajes_dia"]):
        invitados.gastar(u["id"], lim)
    r = cliente(u).post("/api/chat", json={"message": "hola"})
    assert r.status_code == 429 and "límite" in r.json()["error"]


@pytest.mark.asyncio
async def test_caducados_se_desactivan(monkeypatch):
    u = _invitada()
    from contextlib import closing
    from aria import db
    with closing(db._con()) as con, con:
        con.execute("UPDATE invitados SET caduca=? WHERE user_id=?", (time.time() - 1, u["id"]))
    invitados.olvidar_cache()
    assert await api_acceso.caducar_vencidos() == [u["id"]]
    assert not usuarios.por_id(u["id"])["activo"]
    assert await api_acceso.caducar_vencidos() == []


# --- Cloudflare -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_grupo_de_cloudflare_conserva_reglas_y_relleno(monkeypatch):
    monkeypatch.setattr(config, "CF_API_TOKEN", "t")
    monkeypatch.setattr(config, "CF_CUENTA", "c")
    monkeypatch.setattr(config, "CF_GRUPO_INVITADOS", "g")
    grupo = {"name": "Invitados ARIA", "include": [{"email": {"email": cf_access.RELLENO}}, {"email_domain": {"domain": "x.org"}}]}
    puestos = []

    async def pedir(metodo, **kw):
        if metodo == "PUT":
            puestos.append(kw["json"])
            grupo["include"] = kw["json"]["include"]
        return grupo
    monkeypatch.setattr(cf_access, "_pedir", pedir)
    assert await cf_access.anadir("Lucia@Example.com") is True
    assert await cf_access.anadir("lucia@example.com") is False          # ya estaba: no se toca
    assert await cf_access.emails() == ["lucia@example.com"]
    assert await cf_access.quitar("lucia@example.com") is True
    assert {"email_domain": {"domain": "x.org"}} in grupo["include"] and cf_access.RELLENO in cf_access._emails(grupo["include"])
    assert len(puestos) == 2


# --- Telegram ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_telegram_avisa_y_aprueba(monkeypatch):
    admin = usuarios.crear("jefa@example.com", "Jefa", "admin")
    enviados = []

    class Bot:
        async def llamar(self, metodo, **datos):
            enviados.append((metodo, datos))
            return {"message_id": 1}
    monkeypatch.setattr(telegram, "bot", lambda: Bot())
    monkeypatch.setattr(telegram, "chats_de", lambda uid: [{"chat_id": 99}] if uid == admin["id"] else [])
    s = _pedir()
    assert await telegram.avisar_solicitud(s["id"]) == 1
    texto = next(d for m, d in enviados if m == "sendMessage")
    assert "Lucía" in texto["text"] and "Aprobar" not in texto["text"] and texto["reply_markup"]["inline_keyboard"]
    r = await telegram._accion(Bot(), {"message": {"chat": {"id": 99}, "message_id": 1}}, 99, admin, "acceso",
                               {"sid": s["id"], "op": "visita"})
    assert r == "Aprobada." and invitados.solicitud(s["id"])["estado"] == "aprobada"
    normal = usuarios.crear("normal@example.com", "Normal", "usuario")
    assert "administrador" in await telegram._accion(Bot(), {}, 99, normal, "acceso", {"sid": s["id"], "op": "rechazar"})


# --- «Probar como…» (administradores) -----------------------------------------------------------------------------------
def test_admin_prueba_perfiles_y_vuelve():
    admin = usuarios.crear("jefa@example.com", "Jefa", "admin")
    c = cliente(admin)
    assert c.post("/api/vista", json={"perfil": "visita"}).json() == {"vista": "visita"}
    info = c.get("/api/info").json()
    assert info["vista"] == "visita" and info["rol"] == "usuario" and info["limites"]["perfil"] == "visita"
    assert c.get("/api/finanzas/resumen").status_code == 403      # Visita no tiene Finanzas
    assert c.get("/api/acceso").status_code == 403                 # ni nada de administración
    assert c.get("/api/informacion/temas").status_code == 200
    c.post("/api/vista", json={"perfil": "usuario"})
    info = c.get("/api/info").json()
    assert info["rol"] == "usuario" and info["limites"] is None and c.get("/api/finanzas/resumen").status_code == 200
    assert c.post("/api/vista", json={"perfil": None}).json() == {"vista": None}
    c.cookies.delete(main.VISTA_COOKIE)
    assert c.get("/api/info").json()["rol"] == "admin" and c.get("/api/acceso").status_code == 200


def test_un_usuario_no_puede_usar_la_vista():
    u = usuarios.crear("normal@example.com", "Normal", "usuario")
    c = cliente(u)
    assert c.post("/api/vista", json={"perfil": "familiar"}).status_code == 403
    c.cookies.set(main.VISTA_COOKIE, "familiar")
    assert c.get("/api/info").json()["vista"] is None


def test_vista_desconocida_se_ignora():
    admin = usuarios.crear("jefa@example.com", "Jefa", "admin")
    c = cliente(admin)
    assert c.post("/api/vista", json={"perfil": "admin-supremo"}).json() == {"vista": None}
    c.cookies.set(main.VISTA_COOKIE, "admin-supremo")
    assert c.get("/api/info").json()["rol"] == "admin"
