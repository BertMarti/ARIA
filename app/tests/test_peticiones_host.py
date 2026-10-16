"""Pruebas de las peticiones firmadas al agente de la Pi (`aria.telemetria`: solicitar, resultado y
estado_tunel) y de los comandos /copia y /tunel del bot de Telegram, con un bot falso y sin red."""
import asyncio
import hashlib
import hmac
import json

import pytest

from aria import avisos, config, telemetria, telegram as tg, usuarios


class BotFalso:
    def __init__(self):
        self.llamadas = []

    async def llamar(self, metodo, **datos):
        self.llamadas.append((metodo, datos))
        return {"message_id": 1}

    def textos(self):
        return [d.get("text") for m, d in self.llamadas if m == "sendMessage"]

    def ultimo(self, metodo="sendMessage"):
        return next(d for m, d in reversed(self.llamadas) if m == metodo)


@pytest.fixture(autouse=True)
def peticiones_limpias(monkeypatch):
    monkeypatch.setattr(telemetria, "_ultimas", {})


@pytest.fixture(autouse=True)
def limites(monkeypatch):
    for n in ("_lim_mensajes", "_lim_aviso_rapido", "_lim_desconocido", "_lim_vincular", "_lim_vincular_global"):
        viejo = getattr(tg, n)
        monkeypatch.setattr(tg, n, avisos.Limitador(viejo.n, viejo.ventana))


def correr(c):
    return asyncio.run(c)


def msg(chat_id, texto, de=None):
    return {"update_id": 1, "message": {"message_id": 1, "chat": {"id": chat_id, "type": "private"},
                                        "from": {"id": de or chat_id, "first_name": "Al"}, "text": texto}}


def vincular(bot, u, chat_id):
    c = tg.crear_codigo(u["id"])
    correr(tg.procesar(msg(chat_id, f"/start {c['codigo']}"), bot))
    assert tg.chat_vinculado(chat_id)["user_id"] == u["id"]


def botones(teclado):
    return [b for fila in teclado["inline_keyboard"] for b in fila]


def test_solicitar_copia_firma_valida_y_no_se_repite(tmp_path):
    telemetria.solicitar("copia")
    d = json.loads((tmp_path / "host" / "peticiones" / "copia.json").read_text(encoding="utf-8"))
    esperada = hmac.new(config.SECRET.encode(), f"copia:{int(d['ts'])}:{d['nonce']}".encode(),
                        hashlib.sha256).hexdigest()
    assert hmac.compare_digest(d["firma"], esperada)
    assert isinstance(d["ts"], int) and 16 <= len(d["nonce"]) <= 64
    with pytest.raises(RuntimeError) as e:
        telemetria.solicitar("copia")
    assert "10 minutos" in str(e.value)
    assert (tmp_path / "host" / "peticiones" / "copia.json").exists()


def test_resultado_filtra_por_desde_y_estado_tunel_lee_su_archivo(tmp_path):
    res = tmp_path / "host" / "resultados"
    res.mkdir(parents=True)
    (res / "copia.json").write_text(json.dumps({"ts": 1000.0, "estado": "ok", "detalle": ""}), encoding="utf-8")
    assert telemetria.resultado("copia", desde=500)["estado"] == "ok"
    assert telemetria.resultado("copia", desde=2000) is None
    assert telemetria.resultado("tunel") is None
    (tmp_path / "host" / "tunel.json").write_text(json.dumps({"ts": 1000.0, "estado": "caido", "reinicios": [1.0]}),
                                                  encoding="utf-8")
    assert telemetria.estado_tunel() == {"ts": 1000.0, "estado": "caido", "reinicios": [1.0]}
    (tmp_path / "host" / "tunel.json").write_text("esto no es json", encoding="utf-8")
    assert telemetria.estado_tunel() is None


def test_comando_tunel_admin_recibe_mensaje_con_boton(tmp_path):
    bot = BotFalso()
    admin = usuarios.por_identificador("admin")
    vincular(bot, admin, 101)
    (tmp_path / "host").mkdir(parents=True, exist_ok=True)
    (tmp_path / "host" / "tunel.json").write_text(json.dumps({"ts": 1.0, "estado": "ok", "reinicios": []}),
                                                  encoding="utf-8")
    correr(tg.procesar(msg(101, "/tunel"), bot))
    ultimo = bot.ultimo()
    assert "Túnel de Cloudflare" in ultimo["text"] and "accesible desde fuera" in ultimo["text"]
    kb = botones(ultimo["reply_markup"])
    assert any("Reiniciar túnel" in b["text"] for b in kb)
    assert any(b["text"] == "Cancelar" for b in kb)
    assert all(b.get("callback_data", "").startswith("a:") for b in kb)


def test_comando_copia_solo_lo_puede_pedir_un_administrador(tmp_path):
    bot = BotFalso()
    user = usuarios.crear("normal@example.invalid", "Normal", "usuario")
    vincular(bot, user, 202)
    correr(tg.procesar(msg(202, "/copia"), bot))
    assert bot.textos()[-1] == "Eso solo lo puede hacer un administrador."
    assert not (tmp_path / "host" / "peticiones" / "copia.json").exists()
