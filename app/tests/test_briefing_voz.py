from datetime import date

import pytest
from fastapi.testclient import TestClient

from aria import auth, avisos, briefing_voz, main, resumen_diario, telegram, usuarios, voz

LAN = "https://192.168.1.50"
HOY = date(2026, 10, 10)


def _datos(**extra):
    d = {"saludo": "Buenos días, Ana", "fecha_texto": "sábado, 10 de octubre",
         "tiempo": {"ciudad": "Madrid", "cielo": "poco nuboso", "actual": 15, "min": 6, "max": 21, "lluvia": 60},
         "luz": {"barata": {"hora": 14, "precio": .05}, "cara": {"hora": 20, "precio": .35}, "ahora": {"precio": .27}, "nivel": "cara"},
         "agenda": {"eventos": [{"titulo": "Dentista", "inicio": "2026-10-10T17:30:00", "todo_el_dia": False},
                                {"titulo": "Mercadillo", "inicio": "2026-10-10T00:00:00", "todo_el_dia": True}],
                    "cumpleanos": [{"nombre": "Lucía", "fecha": "2026-10-10"}, {"nombre": "Pablo", "fecha": "2026-10-14"}]},
         "recordatorios": [{"texto": "Regar las plantas", "cuando": "2026-10-10T09:00:00"}],
         "finanzas": {"gastos": 85700, "mes_anterior_mismo_dia": 100000, "presupuestos": [{"categoria": "Ocio", "superado": True}]},
         "inversiones": {"valores": [{"nombre": "IBEX 35", "variacion_dia": .2}, {"nombre": "Bitcoin", "variacion_dia": -2.4}]},
         "cierre": "Que tengas un buen día."}
    d.update(extra)
    return d


def test_guion_cuenta_el_dia_en_orden_y_sin_cifras_de_ahora():
    g = briefing_voz.guion(_datos(), HOY)
    assert g.startswith("Buenos días, Ana. Hoy es sábado, 10 de octubre.")
    assert "entre 6 y 21 grados" in g and "paraguas" in g
    assert "más barata a las 14" in g and "0,27" not in g          # nada de «ahora» (cambia cada hora)
    assert "15 grados" not in g                                      # la temperatura actual tampoco
    assert g.index("todo el día, Mercadillo") < g.index("a las 9:00, Regar") < g.index("a las 17:30, Dentista")
    assert "Tienes 3 cosas" in g and "cumpleaños de Lucía" in g and "Pablo" not in g
    assert "857 euros" in g and "14 % menos" in g and "presupuesto en Ocio" in g
    assert "Bitcoin: baja un 2,4 %" in g and g.endswith("Que tengas un buen día.")
    assert len(g) <= briefing_voz.MAX_GUION


def test_guion_de_casa_solo_si_el_resumen_la_trae():
    sin = briefing_voz.guion(_datos(), HOY)
    assert "En casa" not in sin and "red" not in sin
    con = briefing_voz.guion(_datos(aplicaciones={"problemas": ["SHIELD-DNS no responde"]},
                                    red={"nuevos": [{"nombre": "Móvil"}], "n_desconocidos": 0}), HOY)
    assert "hay que revisar una cosa: SHIELD-DNS no responde" in con and "un dispositivo nuevo" in con
    ok = briefing_voz.guion(_datos(aplicaciones={"problemas": [], "shield": {"bloqueadas": 1284}}), HOY)
    assert "todo en orden, y Ping lleva 1.284 anuncios atrapados" in ok


def test_guion_largo_se_corta_por_frases():
    g = briefing_voz.guion(_datos(cierre="Frase de relleno. " * 120), HOY)
    assert len(g) <= briefing_voz.MAX_GUION and g.endswith(".")


def test_trozos_respetan_el_limite_de_la_voz():
    texto = "Una frase corta de prueba. " * 80
    trozos = briefing_voz._trozos(texto)
    assert len(trozos) > 1 and all(len(t) <= voz.MAX_TTS for t in trozos)
    assert " ".join(trozos).split() == texto.split()


def _wav(segundos=1.0):
    return voz._pcm_a_wav(b"\0\0" * int(24000 * segundos))


@pytest.fixture
def ana(monkeypatch):
    u = usuarios.crear("ana@example.com", "Ana", "usuario", "clave-larga-ana")
    resumen_diario._cache.clear()

    async def resumen(usuario, refrescar=False):
        return _datos()
    monkeypatch.setattr(resumen_diario, "construir_resumen_diario", resumen)
    return u


@pytest.mark.asyncio
async def test_audio_se_sintetiza_una_vez_y_se_guarda(ana, monkeypatch):
    llamadas = []

    async def sintetizar(texto, vel, pref=None):
        llamadas.append(texto)
        return _wav(), "gemini"
    monkeypatch.setattr(voz, "sintetizar_info", sintetizar)
    wav1, motor1, guion = await briefing_voz.audio(ana)
    n = len(llamadas)
    wav2, motor2, _ = await briefing_voz.audio(ana)
    assert n >= 1 and len(llamadas) == n                # una síntesis por trozo la primera vez; ninguna la segunda
    assert motor1 == "gemini" and motor2 == "guardado" and wav1 == wav2
    assert voz.duracion_wav(wav1) >= n * 1.0            # trozos unidos (con un respiro entre ellos)
    assert list(briefing_voz._dir().glob("*.wav")) and guion.startswith("Buenos días")


@pytest.mark.asyncio
async def test_voz_local_no_se_guarda_para_reintentar_con_gemini(ana, monkeypatch):
    async def sintetizar(texto, vel, pref=None):
        return _wav(.5), "local"
    monkeypatch.setattr(voz, "sintetizar_info", sintetizar)
    _, motor, _ = await briefing_voz.audio(ana)
    assert motor == "local" and not list(briefing_voz._dir().glob("*.wav"))


@pytest.mark.asyncio
async def test_motores_mezclados_se_rehacen_con_la_voz_local(ana, monkeypatch):
    motores = iter(["gemini", "local", "local", "local"])

    async def sintetizar(texto, vel, pref=None):
        return _wav(.2), next(motores)

    async def local(texto, vel, voz_="auto"):
        return _wav(.3)
    monkeypatch.setattr(voz, "sintetizar_info", sintetizar)
    monkeypatch.setattr(voz, "sintetizar_local", local)
    _, motor, _ = await briefing_voz.audio(ana)
    assert motor == "local"


def test_api_guion_y_audio(ana, monkeypatch):
    async def audio(usuario, refrescar=False):
        return _wav(), "gemini", "Hola"
    monkeypatch.setattr(briefing_voz, "audio", audio)
    c = TestClient(main.app, base_url=LAN)
    c.cookies.set(auth.COOKIE, auth.crear_sesion(ana))
    g = c.get("/api/resumen-diario/hablado")
    assert g.status_code == 200 and g.json()["guion"].startswith("Buenos días, Ana")
    r = c.get("/api/resumen-diario/voz")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.headers["x-voz-motor"] == "gemini"


def test_ajuste_de_voz_del_briefing():
    assert avisos.ajustes_defecto()["briefing"]["voz"] is True
    assert avisos.normalizar_ajustes({"briefing": {"voz": False}})["briefing"]["voz"] is False
    assert avisos.normalizar_ajustes({"briefing": {"voz": "no"}})["briefing"]["voz"] is True


@pytest.mark.asyncio
async def test_telegram_manda_nota_de_voz(ana, monkeypatch):
    subidas = []

    class Bot:
        async def llamar(self, *a, **k):
            return True

        async def subir(self, metodo, campo, nombre, contenido, mime, **datos):
            subidas.append((metodo, mime, datos.get("caption")))

    async def audio(usuario, refrescar=False):
        return _wav(), "gemini", "Hola"

    async def ogg(wav):
        return b"OggS", "audio/ogg"
    monkeypatch.setattr(briefing_voz, "audio", audio)
    monkeypatch.setattr(briefing_voz, "ogg", ogg)
    assert await telegram.enviar_briefing_voz(Bot(), 123, ana) is True
    assert subidas == [("sendVoice", "audio/ogg", "🔊 Tu briefing de hoy")]
