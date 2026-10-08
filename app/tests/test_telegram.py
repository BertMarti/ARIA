"""Bot de Telegram con una Bot API falsa: vinculación, rechazo de chats desconocidos, permisos de comandos,
confirmaciones con botones, troceado de mensajes, HTML escapado, chat y notas de voz."""
import asyncio
import re
import time

import pytest

from aria import avisos, chat, db, recordatorios, telegram as tg, usuarios, voz_puente


class FalsoBot:
    def __init__(self):
        self.llamadas = []
        self.subidas = []
        self.html_roto = False

    async def llamar(self, metodo, espera=20, **d):
        self.llamadas.append((metodo, d))
        if metodo == "sendMessage" and self.html_roto and d.get("parse_mode") == "HTML":
            raise tg.TelegramError(400, "Bad Request: can't parse entities")
        if metodo == "getMe":
            return {"id": 1, "username": "aria_casa_bot"}
        if metodo == "getFile":
            return {"file_path": "voice/file_1.oga"}
        return {"message_id": len(self.llamadas)}

    async def subir(self, metodo, campo, nombre, contenido, mime, **d):
        self.subidas.append((metodo, nombre, mime, contenido, d))
        return {}

    async def descargar(self, ruta, maximo=0):
        return b"OggS-audio-falso"

    def textos(self):
        return [d.get("text") for m, d in self.llamadas if m == "sendMessage"]

    def ultimo(self, metodo="sendMessage"):
        return next(d for m, d in reversed(self.llamadas) if m == metodo)


@pytest.fixture(autouse=True)
def limites(monkeypatch):
    for n in ("_lim_mensajes", "_lim_aviso_rapido", "_lim_desconocido", "_lim_vincular", "_lim_vincular_global"):
        viejo = getattr(tg, n)
        monkeypatch.setattr(tg, n, avisos.Limitador(viejo.n, viejo.ventana))


@pytest.fixture
def bot():
    return FalsoBot()


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def correr(c):
    return asyncio.run(c)


def msg(chat_id, texto=None, tipo="private", **extra):
    m = {"message_id": 1, "chat": {"id": chat_id, "type": tipo}, "from": {"id": chat_id, "first_name": "Al"}, **extra}
    if texto is not None:
        m["text"] = texto
    return {"update_id": 1, "message": m}


def pulsar(chat_id, dato, de=None):
    return {"update_id": 2, "callback_query": {"id": "cq1", "from": {"id": de or chat_id}, "data": dato,
                                               "message": {"message_id": 9, "chat": {"id": chat_id, "type": "private"}}}}


def vincular(bot, u, chat_id):
    c = tg.crear_codigo(u["id"])
    correr(tg.procesar(msg(chat_id, f"/start {c['codigo']}"), bot))
    assert tg.chat_vinculado(chat_id)["user_id"] == u["id"]


def fichas(teclado):
    return [b.get("callback_data") for fila in teclado["inline_keyboard"] for b in fila if b.get("callback_data")]


# --- Vinculación ------------------------------------------------------------------------------------------
def test_vincular_con_codigo_de_un_solo_uso(bot, admin):
    c = tg.crear_codigo(admin["id"])
    assert re.fullmatch(r"\d{6}", c["codigo"])
    correr(tg.procesar(msg(100, f"/start {c['codigo']}"), bot))
    assert tg.chat_vinculado(100)["user_id"] == admin["id"] and "vinculado" in bot.textos()[-1]
    correr(tg.procesar(msg(200, f"/start {c['codigo']}"), bot))  # ya usado
    assert tg.chat_vinculado(200) is None and "no es válido" in bot.textos()[-1]
    assert tg.chats_de(admin["id"])[0]["chat_id"] == 100


def test_codigo_caducado(bot, admin):
    c = tg.crear_codigo(admin["id"], ahora=time.time() - tg.CODIGO_S - 5)
    correr(tg.procesar(msg(100, f"/start {c['codigo']}"), bot))
    assert tg.chat_vinculado(100) is None


def test_varios_chats_y_desvincular(bot, admin, ana):
    vincular(bot, admin, 100)
    vincular(bot, admin, 101)
    assert [c["chat_id"] for c in tg.chats_de(admin["id"])] == [100, 101]
    assert not tg.desvincular(ana["id"], 100)  # solo el dueño
    assert tg.desvincular(admin["id"], 100) and [c["chat_id"] for c in tg.chats_de(admin["id"])] == [101]


def test_fuerza_bruta_del_codigo_limitada(bot, admin):
    for i in range(8):
        correr(tg.procesar(msg(300, f"/start {i:06d}"), bot))
    assert len([t for t in bot.textos() if "no es válido" in t]) == 5


def test_chat_desconocido_rechazado_y_limitado(bot, monkeypatch):
    llamado = []
    monkeypatch.setattr(chat, "conversar", lambda *a, **k: llamado.append(1))
    for t in ("hola", "/estado", "/nuevovpn x"):
        correr(tg.procesar(msg(555, t), bot))
    assert bot.textos() == [tg.NO_TE_CONOZCO] and not llamado


def test_grupos_ignorados(bot, admin):
    vincular(bot, admin, 100)
    n = len(bot.llamadas)
    correr(tg.procesar(msg(100, "hola", tipo="group"), bot))
    correr(tg.procesar(msg(-100123, "/estado", tipo="supergroup"), bot))
    assert len(bot.llamadas) == n


def test_usuario_desactivado_pierde_el_chat(bot, admin, ana):
    vincular(bot, ana, 400)
    usuarios.actualizar(ana["id"], activo=False)
    correr(tg.procesar(msg(400, "hola"), bot))
    assert bot.textos()[-1] == tg.NO_TE_CONOZCO and tg.chat_vinculado(400) is None


def test_api_vincular(admin, monkeypatch, bot):
    from fastapi.testclient import TestClient
    from aria import auth, main
    c = TestClient(main.app, base_url="https://192.168.1.50")
    c.cookies.set(auth.COOKIE, auth.crear_sesion(admin))
    assert c.post("/api/telegram/vincular").status_code == 400  # sin token
    monkeypatch.setattr(tg.config, "TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setattr(tg, "_bot", bot)
    monkeypatch.setattr(tg, "_yo", {})
    d = c.post("/api/telegram/vincular").json()
    assert d["enlace"] == f"https://t.me/aria_casa_bot?start={d['codigo']}"
    vincular(bot, admin, 100)
    info = c.get("/api/avisos/ajustes").json()["telegram"]
    assert info["configurado"] and info["bot"] == "aria_casa_bot" and info["chats"][0]["chat_id"] == 100
    assert c.delete("/api/telegram/chats/100").status_code == 200 and tg.chats_de(admin["id"]) == []


# --- Comandos y permisos -----------------------------------------------------------------------------------------
def test_ayuda_segun_rol(bot, admin, ana):
    vincular(bot, ana, 200)
    correr(tg.procesar(msg(200, "/ayuda"), bot))
    assert "/nuevovpn" not in bot.textos()[-1] and "/recordatorios" in bot.textos()[-1]
    vincular(bot, admin, 100)
    correr(tg.procesar(msg(100, "/ayuda"), bot))
    assert "/nuevovpn" in bot.textos()[-1]


def test_comando_desconocido_no_va_al_chat(bot, admin, monkeypatch):
    vincular(bot, admin, 100)
    monkeypatch.setattr(chat, "conversar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no")))
    correr(tg.procesar(msg(100, "/rm -rf"), bot))
    assert "No conozco ese comando" in bot.textos()[-1]


def test_nuevovpn_solo_admin_y_con_confirmacion(bot, admin, ana, monkeypatch):
    from aria import vpn
    creados = []

    async def listar():
        return []

    async def crear(nombre):
        creados.append(nombre)
        return 7

    async def conf(cid):
        return b"[Interface]\nPrivateKey = secreta\n"
    monkeypatch.setattr(vpn, "listar", listar)
    monkeypatch.setattr(vpn, "crear", crear)
    monkeypatch.setattr(vpn, "configuracion", conf)
    vincular(bot, ana, 200)
    correr(tg.procesar(msg(200, "/nuevovpn movil"), bot))
    assert "administrador" in bot.textos()[-1] and not creados
    vincular(bot, admin, 100)
    correr(tg.procesar(msg(100, "/nuevovpn movil de Ana"), bot))
    pregunta = bot.ultimo()
    assert "clave privada" in pregunta["text"] and not creados
    ok, no = fichas(pregunta["reply_markup"])
    correr(tg.procesar(pulsar(100, ok), bot))
    assert creados == ["movil de Ana"]
    metodos = [s[0] for s in bot.subidas]
    assert metodos == ["sendPhoto", "sendDocument"]
    assert bot.subidas[0][3][:8] == b"\x89PNG\r\n\x1a\n" and bot.subidas[1][1] == "movil_de_Ana.conf"
    assert "CLAVE PRIVADA" in bot.subidas[1][4]["caption"]
    correr(tg.procesar(pulsar(100, ok), bot))  # ficha de un solo uso
    assert creados == ["movil de Ana"]
    assert bot.ultimo("answerCallbackQuery")["text"] == "Este botón ya no sirve."


def test_confirmar_vuelve_a_comprobar_el_rol(bot, admin, monkeypatch):
    from aria import shield
    pausas = []

    async def pausar(m):
        pausas.append(m)
    monkeypatch.setattr(shield, "pausar", pausar)
    otro = usuarios.crear("bea@example.com", "Bea", "admin", "clave-larga-bea")
    vincular(bot, otro, 300)
    f = tg.ficha(300, otro["id"], "confirmar", {"op": "pausar", "min": 5})
    usuarios.actualizar(otro["id"], rol="usuario")  # le quitan el rol entre el botón y la confirmación
    correr(tg.procesar(pulsar(300, f), bot))
    assert pausas == [] and "administrador" in bot.ultimo("answerCallbackQuery")["text"]


def test_anuncios_pausa_en_dos_pasos(bot, admin, ana, monkeypatch):
    from aria import shield
    pausas = []

    async def resumen():
        return {"bloqueo_activo": True, "consultas": 1000, "bloqueadas": 250, "porcentaje": 25.0}

    async def pausar(m):
        pausas.append(m)
    monkeypatch.setattr(shield, "configurado", lambda: True)
    monkeypatch.setattr(shield, "resumen", resumen)
    monkeypatch.setattr(shield, "pausar", pausar)
    vincular(bot, ana, 200)
    correr(tg.procesar(msg(200, "/anuncios"), bot))
    assert "reply_markup" not in bot.ultimo() and "250" in bot.ultimo()["text"]
    vincular(bot, admin, 100)
    correr(tg.procesar(msg(100, "/anuncios"), bot))
    p5, p30, reanudar = fichas(bot.ultimo()["reply_markup"])
    correr(tg.procesar(pulsar(100, p30), bot))
    assert pausas == [] and "30 minutos" in bot.ultimo()["text"]
    ok, _ = fichas(bot.ultimo()["reply_markup"])
    correr(tg.procesar(pulsar(100, ok), bot))
    assert pausas == [30]


def test_fichas_ligadas_al_chat_y_con_caducidad(bot, admin, ana):
    vincular(bot, admin, 100)
    vincular(bot, ana, 200)
    f = tg.ficha(100, admin["id"], "cancelar")
    assert tg.gastar_ficha(f, 200) is None          # otro chat
    f = tg.ficha(100, admin["id"], "cancelar")
    correr(tg.procesar(pulsar(100, f, de=999), bot))  # otro remitente
    assert bot.ultimo("answerCallbackQuery")["text"] == "Este botón ya no sirve."
    f = tg.ficha(100, admin["id"], "cancelar", dura_s=-1)
    assert tg.gastar_ficha(f, 100) is None          # caducada
    assert tg.gastar_ficha("a:inventada", 100) is None and tg.gastar_ficha("rm -rf /", 100) is None
    f = tg.ficha(100, admin["id"], "cancelar")
    tg.desvincular(admin["id"], 100)
    assert tg.gastar_ficha(f, 100) is None          # chat desvinculado


def test_desvincular_desde_telegram(bot, admin):
    vincular(bot, admin, 100)
    correr(tg.procesar(msg(100, "/desvincular"), bot))
    ok, _ = fichas(bot.ultimo()["reply_markup"])
    correr(tg.procesar(pulsar(100, ok), bot))
    assert tg.chat_vinculado(100) is None


def test_estado_y_gastos(bot, ana, monkeypatch):
    from aria import finanzas, services, sistema

    async def estado():
        return {"shield_dns": {"dns_ok": True, "web_ok": True}, "heimdall": {"web_ok": False}}
    monkeypatch.setattr(services, "estado", estado)
    monkeypatch.setattr(sistema, "estado", lambda: {"temperatura": 51.5, "memoria": {"porcentaje": 40.0},
                                                    "disco": {"porcentaje": 30.0}, "uptime_texto": "2 d 3 h"})
    vincular(bot, ana, 200)
    correr(tg.procesar(msg(200, "/estado"), bot))
    t = bot.ultimo()["text"]
    assert "HEIMDALL (VPN): NO responde" in t and "51,5 °C" in t and "<b>Estado de la casa</b>" in t
    finanzas.registrar(ana["id"], None, "Mercadona", -42.5)
    correr(tg.procesar(msg(200, "/gastos"), bot))
    assert "42,50" in bot.ultimo()["text"]


# --- Chat ---------------------------------------------------------------------------------------------------------------
def _responder_falso(monkeypatch, texto="Hola, soy **ARIA**.", vistos=None):
    async def responder(msgs, rol="admin", quien=None, **kw):
        if vistos is not None:
            vistos.append((rol, msgs[-1]["content"]))
        yield {"type": "cerebro", "etiqueta": "falso"}
        yield {"type": "token", "text": "Voy a mirar…"}
        yield {"type": "herramienta", "name": "fecha_hora", "args": {}}
        yield {"type": "resultado", "name": "fecha_hora", "text": "x"}
        yield {"type": "token", "text": texto}
        yield {"type": "fin"}
    monkeypatch.setattr(chat, "responder", responder)

    async def enrutar(texto, rol, clasificador=None):
        return "aria", "general"
    monkeypatch.setattr(chat.agentes, "enrutar", enrutar)


def test_texto_por_el_mismo_chat_con_el_rol_del_usuario(bot, ana, monkeypatch):
    vistos = []
    _responder_falso(monkeypatch, vistos=vistos)
    vincular(bot, ana, 200)
    correr(tg.procesar(msg(200, "¿qué hora es?"), bot))
    assert vistos == [("usuario", "¿qué hora es?")]
    assert bot.textos()[-1] == "Hola, soy <b>ARIA</b>."  # sin el «Voy a mirar…» previo a la herramienta
    assert ("sendChatAction", {"chat_id": 200, "action": "typing"}) in bot.llamadas
    cid = tg.chat_vinculado(200)["conv_id"]
    conv = db.obtener(cid, ana["id"])
    assert conv["titulo"].startswith("Telegram · ") and conv["mensajes"][0]["content"] == "¿qué hora es?"
    correr(tg.procesar(msg(200, "¿y mañana?"), bot))
    assert tg.chat_vinculado(200)["conv_id"] == cid  # misma conversación
    correr(tg.procesar(msg(200, "/nuevo"), bot))
    correr(tg.procesar(msg(200, "otra cosa"), bot))
    assert tg.chat_vinculado(200)["conv_id"] != cid


def test_limite_de_mensajes_por_chat(bot, admin, monkeypatch):
    _responder_falso(monkeypatch)
    monkeypatch.setattr(tg, "_lim_mensajes", avisos.Limitador(2, 60))
    vincular(bot, admin, 100)
    for _ in range(4):
        correr(tg.procesar(msg(100, "hola"), bot))
    assert bot.textos().count("Demasiados mensajes seguidos; espera un minuto.") == 1


def test_nota_de_voz_con_transcriptor_falso(bot, admin, monkeypatch):
    vistos = []
    _responder_falso(monkeypatch, "Son las 10.", vistos)

    async def transcribir(datos, mime="audio/ogg"):
        assert datos.startswith(b"OggS") and mime == "audio/ogg"
        return "qué hora es <b>"
    sintetizados = []

    async def sintetizar(texto):
        sintetizados.append(texto)
        return b"OggS-respuesta", "audio/ogg"
    monkeypatch.setattr(voz_puente, "transcribir", transcribir)
    monkeypatch.setattr(voz_puente, "sintetizar", sintetizar)
    vincular(bot, admin, 100)
    voz = {"file_id": "abc", "duration": 3, "mime_type": "audio/ogg", "file_size": 5000}
    correr(tg.procesar(msg(100, voice=voz), bot))
    assert "<i>qué hora es &lt;b&gt;</i>" in bot.textos() and bot.textos()[-1] == "Son las 10."
    assert vistos[-1][1] == "qué hora es <b>" and sintetizados == [] and bot.subidas == []  # voz desactivada
    avisos.guardar_ajustes(admin["id"], {"voz_telegram": True})
    correr(tg.procesar(msg(100, voice=voz), bot))
    assert sintetizados == ["Son las 10."] and bot.subidas[-1][0] == "sendVoice"
    larga = {**voz, "duration": 600}
    correr(tg.procesar(msg(100, voice=larga), bot))
    assert "demasiado larga" in bot.textos()[-1]


def test_nota_de_voz_sin_transcripcion(bot, admin, monkeypatch):
    async def transcribir(datos, mime="audio/ogg"):
        raise voz_puente.VozError("No puedo transcribir notas de voz.")
    monkeypatch.setattr(voz_puente, "transcribir", transcribir)
    vincular(bot, admin, 100)
    correr(tg.procesar(msg(100, voice={"file_id": "x", "duration": 2}), bot))
    assert bot.textos()[-1] == "No puedo transcribir notas de voz."


# --- Troceado y HTML ------------------------------------------------------------------------------------------------------
def test_html_escapado():
    h = tg.a_html('<script>alert("x")</script> & **negrita** y *cursiva* `a<b` [web](https://e.com/?a=1&b="2") '
                  '[mal](javascript:alert(1)) snake_case_name')
    assert "<script>" not in h and "&lt;script&gt;" in h and "&amp;" in h
    assert "<b>negrita</b>" in h and "<i>cursiva</i>" in h and "<code>a&lt;b</code>" in h
    assert '<a href="https://e.com/?a=1&amp;b=&quot;2&quot;">web</a>' in h
    assert "javascript:" in h and 'href="javascript' not in h
    assert "snake_case_name" in h


def test_html_bloques_titulos_y_listas():
    h = tg.a_html("# Título\n- uno\n- dos\n```python\nprint('<x>')\n```")
    assert h.startswith("<b>Título</b>\n• uno\n• dos") and "<pre>print(&#x27;&lt;x&gt;&#x27;)</pre>" in h


def test_trocear_respeta_el_limite_y_los_bloques():
    texto = "\n\n".join(f"Párrafo {i} " + "palabra " * 60 for i in range(40))
    trozos = tg.trocear(texto)
    assert len(trozos) > 1 and all(len(t) <= tg.TROZO for t in trozos)
    assert " ".join(" ".join(trozos).split()) == " ".join(texto.split())
    codigo = "```\n" + "\n".join(f"linea {i}" for i in range(900)) + "\n```"
    for t in tg.trocear(codigo):
        assert t.count("```") % 2 == 0 and len(t) <= tg.TROZO + 8
    sin_espacios = "x" * 10000
    assert [len(t) for t in tg.trocear(sin_espacios)] == [tg.TROZO, tg.TROZO, 10000 - 2 * tg.TROZO]


def test_enviar_largo_con_botones_en_el_ultimo(bot):
    texto = "\n".join("línea <" + str(i) + "> " + "a" * 80 for i in range(200))
    k = tg.teclado([tg.boton("OK", "a:x")])
    correr(tg.enviar_texto(bot, 1, texto, k))
    envios = [d for m, d in bot.llamadas if m == "sendMessage"]
    assert len(envios) > 1 and all(len(d["text"]) <= tg.LIMITE for d in envios)
    assert "reply_markup" in envios[-1] and not any("reply_markup" in d for d in envios[:-1])


def test_si_telegram_rechaza_el_html_se_manda_en_plano(bot):
    bot.html_roto = True
    correr(tg.enviar_texto(bot, 1, "**hola**"))
    assert bot.llamadas[-1][1]["text"] == "**hola**" and "parse_mode" not in bot.llamadas[-1][1]


# --- Avisos y recordatorios por Telegram -------------------------------------------------------------------------------------
def test_canal_de_avisos_con_botones(bot, admin, monkeypatch):
    monkeypatch.setattr(tg, "_bot", bot)
    monkeypatch.setattr(tg.config, "URL_PUBLICA", "https://aria.ejemplo.com")
    assert correr(tg.canal(admin["id"], {"id": 1, "tipo": "tunel", "severidad": "grave", "texto": "x", "enlace": "red"})) is False
    vincular(bot, admin, 100)
    assert correr(tg.canal(admin["id"], {"id": 5, "tipo": "tunel", "severidad": "grave", "texto": "Túnel <caído>",
                                         "enlace": "control"}))
    m = bot.ultimo()
    assert m["text"] == "<b>Importante.</b> Túnel &lt;caído&gt;"
    botones = m["reply_markup"]["inline_keyboard"][0]
    assert botones[0]["text"] == "Marcar como leído" and botones[1]["url"] == "https://aria.ejemplo.com/#control"


def test_recordatorio_por_telegram_y_posponer(bot, admin, monkeypatch):
    monkeypatch.setattr(tg, "_bot", bot)
    monkeypatch.setattr(avisos, "_CANALES", {"telegram": tg.canal})
    vincular(bot, admin, 100)
    r = recordatorios.crear(admin["id"], "llamar al taller", "en 5 minutos")
    correr(recordatorios.disparar_vencidos(time.time() + 400))
    m = bot.ultimo()
    assert m["text"] == "Recordatorio: llamar al taller"
    mas10, mas1h, hecho = fichas(m["reply_markup"])
    assert [b["text"] for b in m["reply_markup"]["inline_keyboard"][0]] == ["+10 min", "+1 h", "Hecho"]
    correr(tg.procesar(pulsar(100, mas1h), bot))
    assert recordatorios.obtener(admin["id"], r["id"])["estado"] == "pendiente"
    assert bot.ultimo("answerCallbackQuery")["text"].startswith("Te lo recuerdo")
    assert ("editMessageReplyMarkup", {"chat_id": 100, "message_id": 9, "reply_markup": {"inline_keyboard": []}}) in bot.llamadas
    assert avisos.no_leidos(admin["id"]) == 0
    correr(tg.procesar(pulsar(100, hecho), bot))
    assert recordatorios.obtener(admin["id"], r["id"])["estado"] == "hecho"


def test_probar_sin_token(monkeypatch, capsys):
    monkeypatch.setattr(tg.config, "TELEGRAM_TOKEN", "")
    assert correr(tg.probar()) == 1 and "vacío" in capsys.readouterr().out


def test_probar_con_token(monkeypatch, capsys, bot):
    monkeypatch.setattr(tg.config, "TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setattr(tg, "_bot", bot)
    assert correr(tg.probar()) == 0 and "@aria_casa_bot" in capsys.readouterr().out


def test_preparar_quita_webhook_y_registra_comandos(monkeypatch):
    b = FalsoBot()

    async def llamar(metodo, espera=20, **d):
        b.llamadas.append((metodo, d))
        return {"getMe": {"username": "x"}, "getWebhookInfo": {"url": "https://viejo"}}.get(metodo, True)
    b.llamar = llamar
    monkeypatch.setattr(tg, "_yo", {})
    assert correr(tg.preparar(b))
    metodos = [m for m, _ in b.llamadas]
    assert metodos == ["getMe", "getWebhookInfo", "deleteWebhook", "setMyCommands"]


# --- Rutinas, red, bloqueo y enlaces --------------------------------------------------------------------------------
def test_preparar_registra_los_comandos_nuevos(monkeypatch):
    b = FalsoBot()
    monkeypatch.setattr(tg, "_yo", {})
    correr(tg.preparar(b))
    cmds = {c["command"] for c in b.ultimo("setMyCommands")["commands"]}
    assert {"tiempo", "red", "bloqueo", "vpn", "resumen", "ayuda", "rutinas"} <= cmds


def test_rutinas_por_telegram(bot, admin, ana, monkeypatch):
    from aria import rutinas
    monkeypatch.setattr(rutinas, "_en_curso", set())
    rutinas.iniciar()
    vincular(bot, ana, 200)
    correr(tg.procesar(msg(200, "/rutinas"), bot))
    assert "No tienes rutinas" in bot.textos()[-1]
    r = rutinas.crear(ana["id"], "usuario", {"nombre": "Tiempo", "prompt": "el tiempo", "horario": "cada hora"})
    otra = rutinas.crear(admin["id"], "admin", {"nombre": "Ajena", "prompt": "x", "horario": "cada hora"})
    correr(tg.procesar(msg(200, "/rutinas"), bot))
    t = bot.ultimo()
    assert "Tiempo" in t["text"] and "Ajena" not in t["text"]
    ejecutar, pausar = fichas(t["reply_markup"])
    vistos = []

    async def ejecutar_falso(rr, canales_=None, ahora=None):
        vistos.append((rr["id"], canales_))
        return {"estado": "ok", "texto": "**Rutina «Tiempo»**\n\nSol."}
    monkeypatch.setattr(rutinas, "ejecutar", ejecutar_falso)
    correr(tg.procesar(pulsar(200, ejecutar), bot))
    assert vistos == [(r["id"], [])] and "Sol." in bot.textos()[-1]
    correr(tg.procesar(pulsar(200, pausar), bot))
    assert not rutinas.obtener(ana["id"], r["id"])["activa"] and "en pausa" in bot.textos()[-1]
    # Una ficha forjada con la rutina de otro usuario no hace nada
    f = tg.ficha(200, ana["id"], "rutina_ejecutar", {"rid": otra["id"]})
    correr(tg.procesar(pulsar(200, f), bot))
    assert len(vistos) == 1 and bot.ultimo("answerCallbackQuery")["text"] == "Esa rutina ya no existe."


def test_solo_un_enlace_ofrece_resumir(bot, ana, monkeypatch):
    vistos = []
    _responder_falso(monkeypatch, texto="Resumen del artículo.", vistos=vistos)
    vincular(bot, ana, 200)
    correr(tg.procesar(msg(200, "https://example.com/noticia"), bot))
    assert vistos == [] and bot.ultimo()["text"] == "¿Quieres que lo resuma?"
    (resumir,) = fichas(bot.ultimo()["reply_markup"])
    correr(tg.procesar(pulsar(200, resumir), bot))
    assert vistos == [("usuario", "Resume este enlace: https://example.com/noticia")]
    assert bot.textos()[-1] == "Resumen del artículo."
    correr(tg.procesar(msg(200, "mira https://example.com y dime"), bot))  # con más texto: va al chat directamente
    assert len(vistos) == 2


def test_red_segun_rol(bot, admin, ana, monkeypatch):
    from aria import red

    async def salud():
        return {"latencia": {"destinos": [{"nombre": "router", "media_ms": 1.5}]}, "dns": "funciona",
                "vpn": "funciona", "velocidad": None, "vpn_clientes": None}

    async def dispositivos():
        return [{"ip": "192.168.0.10", "nombre": "movil", "conocido": True},
                {"ip": "192.168.0.99", "nombre": "", "fabricante": "Espressif", "conocido": False}]
    monkeypatch.setattr(red, "salud", salud)
    monkeypatch.setattr(red, "dispositivos", dispositivos)
    vincular(bot, ana, 200)
    correr(tg.procesar(msg(200, "/red"), bot))
    t = bot.ultimo()["text"]
    assert "1,5 ms" in t and "192.168.0.99" not in t and "Dispositivos" not in t
    vincular(bot, admin, 100)
    correr(tg.procesar(msg(100, "/red"), bot))
    t = bot.ultimo()["text"]
    assert "Dispositivos: 2, sin reconocer: 1" in t and "Espressif (192.168.0.99)" in t


def test_bloqueo_es_el_bloqueador(bot, ana, monkeypatch):
    from aria import shield

    async def resumen():
        return {"bloqueo_activo": True, "consultas": 10, "bloqueadas": 4, "porcentaje": 40.0}
    monkeypatch.setattr(shield, "configurado", lambda: True)
    monkeypatch.setattr(shield, "resumen", resumen)
    vincular(bot, ana, 200)
    correr(tg.procesar(msg(200, "/bloqueo"), bot))
    assert "4 bloqueadas" in bot.ultimo()["text"] and "reply_markup" not in bot.ultimo()
