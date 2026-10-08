"""Visión: validación y limpieza de imágenes, proveedores falsos (sin red), chat web con imagen, tickets → Finanzas
(con IDOR y límites) y fotos por Telegram."""
import asyncio
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from aria import auth, cerebros, db, finanzas, main, telegram as tg, usuarios, vision
from aria.voz import Limitador

LAN = "https://192.168.1.50"
_REAL = httpx.AsyncClient


# --- Imágenes de prueba (bytes hechos a mano: no hace falta Pillow) --------------------------------------
def _seg(marca: int, datos: bytes) -> bytes:
    return bytes([0xFF, marca]) + (len(datos) + 2).to_bytes(2, "big") + datos


EXIF = _seg(0xE1, b"Exif\x00\x00GPS-37.98,-4.10-Canon")
JFIF = _seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
ICC = _seg(0xE2, b"ICC_PROFILE\x00\x01\x01perfil")
JPEG = b"\xff\xd8" + JFIF + EXIF + ICC + _seg(0xFE, b"comentario") + _seg(0xDB, b"\x00" * 65) + \
    _seg(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"datos-de-imagen\xff\x00mas" + b"\xff\xd9"


def _chunk(nombre: bytes, datos: bytes) -> bytes:
    return len(datos).to_bytes(4, "big") + nombre + datos + b"CRC!"


PNG = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", b"\x00" * 13) + _chunk(b"tEXt", b"Author\x00Lucia") + \
    _chunk(b"eXIf", b"MM\x00*GPS") + _chunk(b"IDAT", b"pixeles") + _chunk(b"IEND", b"")


def _riff(nombre: bytes, datos: bytes) -> bytes:
    return nombre + len(datos).to_bytes(4, "little") + datos + (b"\x00" if len(datos) & 1 else b"")


_WEBP_CUERPO = b"WEBP" + _riff(b"VP8X", bytes([0x0C]) + b"\x00" * 9) + _riff(b"VP8 ", b"fotograma") + \
    _riff(b"EXIF", b"GPS-secreto") + _riff(b"XMP ", b"<x/>")
WEBP = b"RIFF" + len(_WEBP_CUERPO).to_bytes(4, "little") + _WEBP_CUERPO


def data_url(datos: bytes, mime="image/jpeg") -> str:
    return f"data:{mime};base64," + base64.b64encode(datos).decode()


# --- Fixtures ----------------------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    monkeypatch.setattr(cerebros, "_esperas", {})
    monkeypatch.setattr(vision, "_tickets", {})
    monkeypatch.setattr(vision, "limite_minuto", Limitador(6, 60))
    monkeypatch.setattr(vision, "limite_hora", Limitador(60, 3600))
    monkeypatch.delenv("ARIA_VISION", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "clave-gemini")
    monkeypatch.setenv("GROQ_API_KEY", "clave-groq")


TICKET_MD = ("Es un ticket de **Mercadona** del 3 de octubre: total 17,04 €.\n\n```ticket\n"
             '{"comercio": "Mercadona", "fecha": "2026-10-03", "total": 17.04, "categoria": "Supermercado"}\n```')


class Falsos:
    """Proveedores de visión falsos: respuestas por host y registro de lo que se envió."""

    def __init__(self, monkeypatch, gemini=(200, TICKET_MD), groq=(200, "Un gato en un sofá.")):
        self.pedidas = []
        self.resp = {"generativelanguage.googleapis.com": gemini, "api.groq.com": groq}

        def atender(req: httpx.Request):
            self.pedidas.append((req.url.host, json.loads(req.content), req.headers.get("authorization")))
            estado, texto = self.resp.get(req.url.host, (599, ""))
            if estado != 200:
                return httpx.Response(estado, json={"error": {"message": texto or "fallo"}})
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": texto}}]})

        monkeypatch.setattr(vision.httpx, "AsyncClient",
                            lambda **kw: _REAL(transport=httpx.MockTransport(atender), **kw))

    def imagen_enviada(self, n=-1) -> bytes:
        partes = self.pedidas[n][1]["messages"][-1]["content"]
        url = next(p["image_url"]["url"] for p in partes if p["type"] == "image_url")
        return base64.b64decode(url.split(",", 1)[1])


@pytest.fixture
def admin():
    return usuarios.por_identificador("admin")


@pytest.fixture
def ana():
    return usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")


def cliente_de(u) -> TestClient:
    c = TestClient(main.app, base_url=LAN, follow_redirects=False)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(u))
    return c


def eventos(r) -> list:
    return [json.loads(l) for l in r.text.splitlines() if l.strip()]


# --- Validación y metadatos ----------------------------------------------------------------------------
def test_tipo_por_bytes_y_tamano():
    assert vision.validar(JPEG) == "image/jpeg"
    assert vision.validar(PNG) == "image/png"
    assert vision.validar(WEBP) == "image/webp"
    for malo, estado in ((b"GIF89a....", 415), (b"<svg/>", 415), (b"", 400), (b"\xff\xd8\xff" + b"0" * vision.MAX_BYTES, 413)):
        with pytest.raises(vision.VisionError) as e:
            vision.validar(malo)
        assert e.value.estado == estado


def test_data_url_no_se_fia_del_tipo_declarado():
    datos, mime = vision.desde_data_url(data_url(PNG, "image/jpeg"))
    assert datos == PNG and mime == "image/png"
    for malo in (None, 3, "data:text/html;base64,PGI+", "http://x/y.jpg", data_url(b"GIF89a-no")):
        with pytest.raises(vision.VisionError):
            vision.desde_data_url(malo)


def test_jpeg_sin_exif_ni_comentarios_conserva_jfif_icc_y_datos():
    limpio = vision.sin_metadatos(JPEG, "image/jpeg")
    assert b"Exif" not in limpio and b"GPS" not in limpio and b"comentario" not in limpio
    assert JFIF in limpio and ICC in limpio and limpio.endswith(b"datos-de-imagen\xff\x00mas\xff\xd9")


def test_png_y_webp_sin_metadatos():
    p = vision.sin_metadatos(PNG, "image/png")
    assert b"tEXt" not in p and b"eXIf" not in p and b"Lucía" not in p and b"IDAT" in p and p.endswith(b"IEND" + b"CRC!")
    w = vision.sin_metadatos(WEBP, "image/webp")
    assert b"GPS" not in w and b"XMP " not in w and b"fotograma" in w
    assert int.from_bytes(w[4:8], "little") == len(w) - 8
    assert w[20] & 0x0C == 0  # marcas EXIF/XMP del VP8X apagadas


def test_jpeg_danado():
    with pytest.raises(vision.VisionError):
        vision.sin_metadatos(b"\xff\xd8\xff\xe1\x00\xff", "image/jpeg")


def test_extraer_ticket(admin):
    texto, t = vision.extraer_ticket(TICKET_MD, admin["id"])
    assert "```" not in texto and "Mercadona" in texto
    assert t == {"comercio": "Mercadona", "fecha": "2026-10-03", "total": 1704, "categoria": "Supermercado"}
    # categoría inventada -> automática; total con coma; sin bloque -> None
    _, t2 = vision.extraer_ticket('```json\n{"comercio":"Bar Pepe","fecha":null,"total":"3,50","categoria":"Cervezas"}\n```',
                                  admin["id"])
    assert t2["categoria"] is None and t2["total"] == 350 and t2["fecha"]
    assert vision.extraer_ticket("Un gato.", admin["id"]) == ("Un gato.", None)
    assert vision.extraer_ticket('```ticket\n{"comercio":"X","total":0}\n```', admin["id"])[1] is None


# --- Proveedores ----------------------------------------------------------------------------------------
def test_gemini_principal_y_sin_exif(monkeypatch, admin):
    f = Falsos(monkeypatch)
    r = asyncio.run(vision.analizar(JPEG, "image/jpeg", "¿Qué es?", admin))
    assert r["proveedor"] == "gemini" and r["ticket"]["total"] == 1704 and "```" not in r["texto"]
    host, cuerpo, autorizacion = f.pedidas[0]
    assert host == "generativelanguage.googleapis.com" and autorizacion == "Bearer clave-gemini"
    assert cuerpo["model"] == "gemini-3.5-flash-lite" and cuerpo["stream"] is False
    enviada = f.imagen_enviada()
    assert b"Exif" not in enviada and b"GPS" not in enviada and enviada.startswith(b"\xff\xd8")
    assert "Supermercado" in cuerpo["messages"][0]["content"]  # categorías del usuario en el prompt


def test_relevo_a_groq_y_espera(monkeypatch, admin):
    f = Falsos(monkeypatch, gemini=(429, "quota exceeded"))
    r = asyncio.run(vision.analizar(PNG, "image/png", "", admin))
    assert r["proveedor"] == "groq" and r["texto"] == "Un gato en un sofá." and r["ticket"] is None
    assert [h for h, _, _ in f.pedidas] == ["generativelanguage.googleapis.com", "api.groq.com"]
    assert f.pedidas[1][1]["model"] == "qwen/qwen3.8-27b"
    assert cerebros.en_espera("vision_gemini")  # la cuota se recuerda: la siguiente va directa a Groq
    asyncio.run(vision.analizar(PNG, "image/png", "", admin))
    assert [h for h, _, _ in f.pedidas][2:] == ["api.groq.com"]


def test_todos_fallan_y_nunca_el_local(monkeypatch, admin):
    f = Falsos(monkeypatch, gemini=(500, ""), groq=(401, ""))
    with pytest.raises(vision.VisionError) as e:
        asyncio.run(vision.analizar(JPEG, "image/jpeg", "", admin))
    assert e.value.estado == 503 and "no puedo ver imágenes" in e.value.mensaje
    assert {h for h, _, _ in f.pedidas} == {"generativelanguage.googleapis.com", "api.groq.com"}


def test_sin_claves_o_apagada(monkeypatch, admin):
    Falsos(monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.delenv("GROQ_API_KEY")
    assert not vision.disponible()
    with pytest.raises(vision.VisionError):
        asyncio.run(vision.analizar(JPEG, "image/jpeg", "", admin))
    monkeypatch.setenv("GROQ_API_KEY", "k")
    assert [p.id for p in vision.orden()] == ["groq"]
    monkeypatch.setenv("ARIA_VISION", "no")
    assert not vision.disponible()
    monkeypatch.setenv("ARIA_VISION", "groq,gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert [p.id for p in vision.orden()] == ["groq", "gemini"]


def test_cuota_agotada_en_todos(monkeypatch, admin):
    Falsos(monkeypatch, gemini=(429, ""), groq=(429, ""))
    with pytest.raises(vision.VisionError) as e:
        asyncio.run(vision.analizar(JPEG, "image/jpeg", "", admin))
    assert e.value.estado == 429


# --- Chat web -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("quien", ["admin", "ana"])
def test_chat_con_imagen_y_ticket_para_los_dos_roles(monkeypatch, quien, admin, ana):
    u = admin if quien == "admin" else ana
    Falsos(monkeypatch)
    c = cliente_de(u)
    r = c.post("/api/chat", json={"conversation_id": None, "message": "apúntalo", "imagen": data_url(JPEG)})
    assert r.status_code == 200
    ev = eventos(r)
    tipos = [e["type"] for e in ev]
    assert tipos[0] == "conv" and "cerebro" in tipos and tipos[-1] == "fin"
    tk = next(e for e in ev if e["type"] == "ticket")
    assert tk["importe"] == "17,04 €" and tk["comercio"] == "Mercadona" and "datos" not in tk and len(tk["token"]) >= 16
    cid = ev[0]["id"]
    msgs = db.obtener(cid, u["id"])["mensajes"]
    assert msgs[0]["content"] == "[imagen] apúntalo"
    todo = json.dumps(msgs)
    assert "base64" not in todo and "/9j/" not in todo  # la imagen no se guarda
    # Confirmar: el gasto va a las finanzas de ESTE usuario (uid de la sesión)
    r2 = c.post(f"/api/vision/tickets/{tk['token']}")
    assert r2.status_code == 200 and r2.json()["texto"].startswith("Apuntado")
    movs = finanzas.listar(u["id"])
    assert len(movs) == 1 and movs[0]["importe"] == -1704 and movs[0]["fecha"] == "2026-10-03" \
        and movs[0]["categoria"] == "Supermercado"
    assert db.obtener(cid, u["id"])["mensajes"][-1]["content"].startswith("Apuntado")
    assert c.post(f"/api/vision/tickets/{tk['token']}").status_code == 404  # un solo uso


def test_ticket_idor(monkeypatch, admin, ana):
    Falsos(monkeypatch)
    ev = eventos(cliente_de(admin).post("/api/chat", json={"message": "", "imagen": data_url(JPEG)}))
    token = next(e for e in ev if e["type"] == "ticket")["token"]
    c_ana = cliente_de(ana)
    assert c_ana.post(f"/api/vision/tickets/{token}").status_code == 404
    assert c_ana.delete(f"/api/vision/tickets/{token}").status_code == 404
    assert finanzas.listar(ana["id"]) == [] and finanzas.listar(admin["id"]) == []
    # el intento ajeno no gasta la propuesta: su dueño aún puede descartarla
    assert cliente_de(admin).delete(f"/api/vision/tickets/{token}").status_code == 200
    assert cliente_de(admin).post(f"/api/vision/tickets/{token}").status_code == 404
    assert finanzas.listar(admin["id"]) == []
    # la conversación del admin tampoco es de Ana
    cid = ev[0]["id"]
    r = c_ana.post("/api/chat", json={"conversation_id": cid, "message": "", "imagen": data_url(JPEG)})
    assert eventos(r)[0]["id"] != cid


def test_ticket_caduca(monkeypatch, admin):
    t = {"comercio": "X", "fecha": "2026-10-01", "total": 100, "categoria": None}
    token = vision.proponer(admin["id"], t)
    monkeypatch.setattr(vision, "_ahora", lambda: 10 ** 12)
    assert vision.tomar(admin["id"], token) is None


def test_chat_imagen_errores(monkeypatch, admin):
    Falsos(monkeypatch)
    c = cliente_de(admin)
    assert c.post("/api/chat", json={"message": "x", "imagen": data_url(b"GIF89a")}).status_code == 415
    grande = "data:image/jpeg;base64," + "A" * (vision.MAX_BYTES * 4 // 3 + 400)
    assert c.post("/api/chat", json={"message": "x", "imagen": grande}).status_code == 413
    enorme = b'{"message":"x","imagen":"' + b"A" * (main.MAX_CUERPO_CHAT + 10) + b'"}'
    assert c.post("/api/chat", content=enorme, headers={"Content-Type": "application/json"}).status_code == 413
    monkeypatch.setenv("ARIA_VISION", "no")
    r = c.post("/api/chat", json={"message": "x", "imagen": data_url(JPEG)})
    assert r.status_code == 503 and "no puedo ver" in r.json()["error"]
    assert c.get("/api/info").json()["funciones"]["vision"] is False


def test_chat_imagen_limite_por_usuario(monkeypatch, admin, ana):
    Falsos(monkeypatch, gemini=(200, "Una foto."))
    monkeypatch.setattr(vision, "limite_minuto", Limitador(2, 60))
    c = cliente_de(admin)
    for _ in range(2):
        assert c.post("/api/chat", json={"message": "", "imagen": data_url(JPEG)}).status_code == 200
    r = c.post("/api/chat", json={"message": "", "imagen": data_url(JPEG)})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert cliente_de(ana).post("/api/chat", json={"message": "", "imagen": data_url(JPEG)}).status_code == 200


def test_chat_imagen_fallo_de_proveedores_es_evento_error(monkeypatch, admin):
    Falsos(monkeypatch, gemini=(500, ""), groq=(500, ""))
    ev = eventos(cliente_de(admin).post("/api/chat", json={"message": "", "imagen": data_url(PNG)}))
    assert ev[-1]["type"] == "error" and "no puedo ver" in ev[-1]["text"]


def test_chat_sin_imagen_sigue_igual(admin):
    r = cliente_de(admin).post("/api/chat", json={"message": "  "})
    assert r.status_code == 400


def test_token_con_formato_raro(admin):
    c = cliente_de(admin)
    assert c.post("/api/vision/tickets/corto").status_code in (403, 404)


# --- Telegram -------------------------------------------------------------------------------------------
class BotFoto:
    def __init__(self, imagen=JPEG):
        self.llamadas, self.imagen = [], imagen

    async def llamar(self, metodo, espera=20, **d):
        self.llamadas.append((metodo, d))
        if metodo == "getFile":
            return {"file_path": "photos/file_1.jpg"}
        return {"message_id": len(self.llamadas)}

    async def subir(self, *a, **k):
        return {}

    async def descargar(self, ruta, maximo=0):
        assert maximo == vision.MAX_BYTES
        return self.imagen

    def mensajes(self):
        return [d for m, d in self.llamadas if m == "sendMessage"]


@pytest.fixture(autouse=True)
def limites_tg(monkeypatch):
    for n in ("_lim_mensajes", "_lim_aviso_rapido", "_lim_desconocido"):
        viejo = getattr(tg, n)
        monkeypatch.setattr(tg, n, tg.avisos.Limitador(viejo.n, viejo.ventana))


def _vincular(u, chat_id):
    codigo = tg.crear_codigo(u["id"])["codigo"]
    assert tg.canjear_codigo(codigo, chat_id, "Al") == u["id"]


FOTOS = [{"file_id": "p", "width": 90, "height": 90, "file_size": 1000},
         {"file_id": "g", "width": 1280, "height": 960, "file_size": 200000},
         {"file_id": "enorme", "width": 4000, "height": 3000, "file_size": vision.MAX_BYTES + 1}]


def foto(chat_id, **extra):
    return {"update_id": 5, "message": {"message_id": 3, "chat": {"id": chat_id, "type": "private"},
                                        "from": {"id": chat_id}, **extra}}


def pulsar(chat_id, dato):
    return {"update_id": 6, "callback_query": {"id": "cq", "from": {"id": chat_id}, "data": dato,
                                               "message": {"message_id": 9, "chat": {"id": chat_id, "type": "private"}}}}


@pytest.mark.parametrize("quien", ["admin", "ana"])
def test_telegram_foto_ticket_y_registrar(monkeypatch, quien, admin, ana):
    u = admin if quien == "admin" else ana
    f = Falsos(monkeypatch)
    _vincular(u, 300)
    b = BotFoto()
    asyncio.run(tg.procesar(foto(300, photo=FOTOS, caption="¿cuánto fue?"), b))
    assert ("getFile", {"file_id": "g"}) in b.llamadas  # la mayor que cabe en 5 MB
    assert f.pedidas[0][1]["messages"][-1]["content"][0]["text"] == "¿cuánto fue?"
    ultimo = b.mensajes()[-1]
    assert "17,04 €" in ultimo["text"] and "¿Lo apunto" in ultimo["text"]
    botones = ultimo["reply_markup"]["inline_keyboard"][0]
    assert [x["text"] for x in botones] == ["Registrar", "Cancelar"]
    assert all(len(x["callback_data"]) <= 64 for x in botones)
    asyncio.run(tg.procesar(pulsar(300, botones[0]["callback_data"]), b))
    movs = finanzas.listar(u["id"])
    assert len(movs) == 1 and movs[0]["importe"] == -1704
    assert b.mensajes()[-1]["text"].startswith("Apuntado")
    # un solo uso
    asyncio.run(tg.procesar(pulsar(300, botones[0]["callback_data"]), b))
    assert len(finanzas.listar(u["id"])) == 1
    # el historial de la conversación del chat no guarda la imagen
    cid = tg.chat_vinculado(300)["conv_id"]
    msgs = db.obtener(cid, u["id"])["mensajes"]
    assert msgs[0]["content"] == "[imagen] ¿cuánto fue?" and "base64" not in json.dumps(msgs)


def test_telegram_cancelar_y_ficha_de_otro_chat(monkeypatch, admin, ana):
    Falsos(monkeypatch)
    _vincular(admin, 301)
    _vincular(ana, 302)
    b = BotFoto()
    asyncio.run(tg.procesar(foto(301, photo=FOTOS), b))
    si, no = (x["callback_data"] for x in b.mensajes()[-1]["reply_markup"]["inline_keyboard"][0])
    asyncio.run(tg.procesar(pulsar(302, si), b))  # otro chat (de Ana) no puede usar la ficha
    assert finanzas.listar(ana["id"]) == [] and finanzas.listar(admin["id"]) == []
    b2 = BotFoto()
    asyncio.run(tg.procesar(foto(301, photo=FOTOS), b2))
    si2, no2 = (x["callback_data"] for x in b2.mensajes()[-1]["reply_markup"]["inline_keyboard"][0])
    asyncio.run(tg.procesar(pulsar(301, no2), b2))
    assert finanzas.listar(admin["id"]) == []


def test_telegram_foto_sin_ticket_documento_y_errores(monkeypatch, admin):
    Falsos(monkeypatch, gemini=(200, "Un **gato** en un sofá."))
    _vincular(admin, 303)
    b = BotFoto(PNG)
    doc = {"file_id": "d", "mime_type": "image/png", "file_size": 5000}
    asyncio.run(tg.procesar(foto(303, document=doc), b))
    assert "gato" in b.mensajes()[-1]["text"] and "reply_markup" not in b.mensajes()[-1]
    # algo que no es imagen aunque lo diga
    b2 = BotFoto(b"MZ\x90\x00ejecutable")
    asyncio.run(tg.procesar(foto(303, photo=FOTOS), b2))
    assert b2.mensajes()[-1]["text"] == "Solo puedo ver imágenes JPEG, PNG o WebP."
    # todas demasiado grandes
    b3 = BotFoto()
    asyncio.run(tg.procesar(foto(303, photo=[FOTOS[2]]), b3))
    assert "demasiado grande" in b3.mensajes()[-1]["text"]
    # sin proveedores
    monkeypatch.setenv("ARIA_VISION", "no")
    b4 = BotFoto()
    asyncio.run(tg.procesar(foto(303, photo=FOTOS), b4))
    assert b4.mensajes()[-1]["text"] == vision.NO_DISPONIBLE and not any(m == "getFile" for m, _ in b4.llamadas)


def test_telegram_foto_de_chat_desconocido(monkeypatch):
    f = Falsos(monkeypatch)
    b = BotFoto()
    asyncio.run(tg.procesar(foto(999, photo=FOTOS), b))
    assert b.mensajes()[-1]["text"] == tg.NO_TE_CONOZCO and not f.pedidas
    assert not any(m == "getFile" for m, _ in b.llamadas)


def test_telegram_limite_de_imagenes(monkeypatch, admin):
    Falsos(monkeypatch, gemini=(200, "Una foto."))
    monkeypatch.setattr(vision, "limite_minuto", Limitador(1, 60))
    _vincular(admin, 304)
    b = BotFoto()
    asyncio.run(tg.procesar(foto(304, photo=FOTOS), b))
    asyncio.run(tg.procesar(foto(304, photo=FOTOS), b))
    assert b.mensajes()[-1]["text"].startswith("Demasiadas imágenes seguidas")


def test_en_espera_por_cuota_avisa_de_la_cuota(monkeypatch, admin):
    Falsos(monkeypatch, gemini=(429, ""), groq=(429, ""))
    for _ in range(2):  # la segunda vez ambos están en espera y ni se llama a la red
        with pytest.raises(vision.VisionError) as e:
            asyncio.run(vision.analizar(JPEG, "image/jpeg", "", admin))
        assert e.value.estado == 429
