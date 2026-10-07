import asyncio

import httpx
import pytest

from aria import busqueda, permisos, tools

_REAL = httpx.AsyncClient


def falso_searxng(monkeypatch, manejador):
    """Sustituye el cliente HTTP de busqueda por uno que habla con un SearXNG falso (sin red)."""
    llamadas = []

    def atender(req):
        llamadas.append(req)
        return manejador(req)

    monkeypatch.setattr(busqueda.httpx, "AsyncClient",
                        lambda **kw: _REAL(transport=httpx.MockTransport(atender), **{k: v for k, v in kw.items()}))
    return llamadas


@pytest.fixture(autouse=True)
def limpio():
    busqueda._cache.clear()
    yield
    busqueda._cache.clear()


def resultado(i, **extra):
    r = {"title": f"Título {i}", "url": f"https://sitio{i}.es/pagina?id={i}", "content": f"Extracto {i}"}
    r.update(extra)
    return r


def respuesta(*res):
    return lambda req: httpx.Response(200, json={"results": list(res)})


def buscar(*a, **kw):
    return asyncio.run(busqueda.buscar(*a, **kw))


def test_parseo_basico(monkeypatch):
    falso_searxng(monkeypatch, respuesta(resultado(1, publishedDate="2026-10-07T08:30:00"), resultado(2)))
    r = buscar("hola mundo")
    assert r[0] == {"titulo": "Título 1", "url": "https://sitio1.es/pagina?id=1", "dominio": "sitio1.es",
                    "extracto": "Extracto 1", "fecha": "2026-10-07"}
    assert r[1]["fecha"] is None and len(r) == 2


def test_parametros_enviados(monkeypatch):
    ll = falso_searxng(monkeypatch, respuesta(resultado(1)))
    buscar("noticias jaén", "news", 3, "day")
    q = ll[0].url.params
    assert q["format"] == "json" and q["categories"] == "news" and q["time_range"] == "day"
    assert q["language"] == "es-ES" and q["q"] == "noticias jaén"
    assert ll[0].url.host == "searxng"


def test_html_y_entidades_fuera_y_recorte(monkeypatch):
    largo = "<b>Palabra</b> &amp; más " + "texto " * 100
    falso_searxng(monkeypatch, respuesta(resultado(1, content=largo, title="<i>Hola</i>&nbsp;&quot;mundo&quot;")))
    r = buscar("x")[0]
    assert "<" not in r["extracto"] and "&amp;" not in r["extracto"] and r["extracto"].startswith("Palabra & más")
    assert len(r["extracto"]) <= busqueda.MAX_EXTRACTO and r["extracto"].endswith("…")
    assert r["titulo"] == 'Hola "mundo"'


def test_quita_seguimiento_y_solo_http(monkeypatch):
    falso_searxng(monkeypatch, respuesta(
        resultado(1, url="https://www.ejemplo.com/a?utm_source=x&id=7&fbclid=abc&gclid=1#frag"),
        resultado(2, url="javascript:alert(1)"),
        resultado(3, url="ftp://sitio.es/f"),
        resultado(4, url="https://user:pass@malo.es/")))
    r = buscar("x")
    assert [x["url"] for x in r] == ["https://www.ejemplo.com/a?id=7"]
    assert r[0]["dominio"] == "ejemplo.com"


def test_dedupe_por_dominio(monkeypatch):
    falso_searxng(monkeypatch, respuesta(
        resultado(1, url="https://es.wikipedia.org/wiki/A"), resultado(2, url="https://es.wikipedia.org/wiki/B"),
        resultado(3, url="https://www.otro.es/x"), resultado(4, url="https://otro.es/y"), resultado(5)))
    assert [x["dominio"] for x in buscar("x", n=5)] == ["es.wikipedia.org", "otro.es", "sitio5.es"]


def test_respeta_n(monkeypatch):
    falso_searxng(monkeypatch, respuesta(*[resultado(i) for i in range(1, 10)]))
    assert len(buscar("x", n=3)) == 3


def test_cache_diez_minutos(monkeypatch):
    ll = falso_searxng(monkeypatch, respuesta(resultado(1)))
    reloj = [1000.0]
    monkeypatch.setattr(busqueda, "_ahora", lambda: reloj[0])
    buscar("Mismo Tema")
    buscar("  mismo   tema ")
    assert len(ll) == 1
    reloj[0] += busqueda.CACHE_S - 1
    buscar("mismo tema")
    assert len(ll) == 1
    reloj[0] += 2
    buscar("mismo tema")
    assert len(ll) == 2
    buscar("mismo tema", "news")  # otra categoría = otra entrada
    assert len(ll) == 3


def test_vacias_no_se_cachean(monkeypatch):
    ll = falso_searxng(monkeypatch, respuesta())
    assert buscar("nada") == [] and buscar("nada") == []
    assert len(ll) == 2


def test_timeout_mensaje_amigable(monkeypatch):
    def lento(req):
        raise httpx.ReadTimeout("lento")
    falso_searxng(monkeypatch, lento)
    with pytest.raises(busqueda.BusquedaError, match="tardado demasiado"):
        buscar("x")
    assert "tardado demasiado" in asyncio.run(tools.ejecutar("buscar_en_internet", {"consulta": "x"}, "usuario"))


def test_servicio_caido_y_json_roto(monkeypatch):
    falso_searxng(monkeypatch, lambda req: httpx.Response(503))
    with pytest.raises(busqueda.BusquedaError, match="no está disponible"):
        buscar("x")
    falso_searxng(monkeypatch, lambda req: httpx.Response(200, text="<html>no json</html>"))
    with pytest.raises(busqueda.BusquedaError, match="No puedo buscar"):
        buscar("x")

    def sin_red(req):
        raise httpx.ConnectError("no")
    falso_searxng(monkeypatch, sin_red)
    assert "No puedo buscar" in asyncio.run(tools.ejecutar("noticias", {"tema": "x"}, "admin"))


def test_consulta_vacia():
    with pytest.raises(busqueda.BusquedaError, match="qué quieres buscar"):
        buscar("   ")


def test_resultado_compacto_para_el_modelo(monkeypatch):
    falso_searxng(monkeypatch, respuesta(*[resultado(i, content="palabra " * 80, title="T" * 150) for i in range(1, 8)]))
    txt = asyncio.run(tools.ejecutar("buscar_en_internet", {"consulta": "q" * 400}, "admin"))
    assert len(txt) <= 1500
    assert txt.count("https://") >= 3
    assert "Resultados de internet" in txt


def test_sin_resultados_texto(monkeypatch):
    falso_searxng(monkeypatch, respuesta())
    assert "No he encontrado resultados" in asyncio.run(tools.ejecutar("buscar_en_internet", {"consulta": "zzz"}))


def test_noticias_prueba_dia_y_luego_semana(monkeypatch):
    def h(req):
        return httpx.Response(200, json={"results": [resultado(1)] if req.url.params.get("time_range") == "week" else []})
    ll = falso_searxng(monkeypatch, h)
    txt = asyncio.run(tools.ejecutar("noticias", {}, "usuario"))
    assert [r.url.params["time_range"] for r in ll] == ["day", "week"]
    assert "sitio1.es" in txt and all(r.url.params["categories"] == "news" for r in ll)


# --- permisos e intenciones ---
@pytest.mark.parametrize("n", ["buscar_en_internet", "noticias"])
def test_usuario_puede_buscar(n):
    assert n in tools.permitidas("usuario") and n in tools.permitidas("admin")
    assert n in tools.SOLO_LECTURA


def test_usuario_sigue_sin_poder_escribir():
    assert not tools.permitidas("usuario") & {"pausar_bloqueador", "crear_dispositivo_vpn", "spotify_play"}


def test_usuario_puede_chatear_pero_no_llamar_a_busqueda_directamente():
    assert permisos.permitido("usuario", "POST", "/api/chat")  # la búsqueda solo existe como herramienta del chat
    assert not permisos.permitido("usuario", "POST", "/api/busqueda")


@pytest.mark.parametrize("texto,esperada", [
    ("Búscame el horario del tren a Jaén", "buscar_en_internet"),
    ("busca en internet qué es el IPv6", "buscar_en_internet"),
    ("Googlea la receta de salmorejo", "buscar_en_internet"),
    ("¿Cuál es el precio de la luz?", "buscar_en_internet"),
    ("¿Quién ganó el partido de ayer?", "buscar_en_internet"),
    ("¿Cuándo se estrena la nueva película de Marvel?", "buscar_en_internet"),
    ("¿Cuál es el último iPhone?", "buscar_en_internet"),
    ("Dame las noticias de hoy", "noticias"),
    ("Titulares de la actualidad", "noticias"),
    ("¿Qué ha pasado, última hora?", "noticias"),
])
def test_busqueda_se_ofrece(texto, esperada):
    assert esperada in tools.relevantes(texto)


@pytest.mark.parametrize("texto", ["hola", "Hola", "explícame qué es un DNS", "Explícame qué es un DNS",
                                   "¿Qué es una VPN?", "Cuéntame un chiste", "Gracias", "Escribe un poema sobre el mar",
                                   "¿Qué significa latencia?"])
def test_charla_no_activa_busqueda(texto):
    assert not tools.relevantes(texto) & {"buscar_en_internet", "noticias"}


def test_no_choca_con_otras_herramientas():
    assert "buscar_en_internet" not in tools.relevantes("Busca una serie en Netflix")
    assert "buscar_en_internet" not in tools.relevantes("Pon música de Queen")
    assert "buscar_en_internet" not in tools.relevantes("¿Cuántos anuncios has bloqueado hoy?")
    assert "buscar_en_internet" not in tools.relevantes("¿Qué temperatura tiene la Raspberry hoy?")
    assert "buscar_en_internet" not in tools.relevantes("¿Qué hora es?")


def test_prompt_de_nube_pide_citar_fuentes():
    from aria import config
    p = config.system_prompt(True, "Ana", False)
    assert "Fuentes:" in p and "buscar_en_internet" in p
    assert "Fuentes:" not in config.system_prompt(False)


def test_descarta_escrituras_ajenas(monkeypatch):
    falso_searxng(monkeypatch, respuesta(resultado(1, title="树莓派 新闻"), resultado(2, title="Привет"), resultado(3)))
    assert [r["titulo"] for r in buscar("raspberry pi")] == ["Título 3"]
    falso_searxng(monkeypatch, respuesta(resultado(1, title="树莓派 新闻")))
    assert len(buscar("树莓派 新闻 2")) == 1  # si la consulta ya usa esa escritura, se conservan


def test_noticias_completa_con_la_semana(monkeypatch):
    def h(req):
        if req.url.params["time_range"] == "day":
            return httpx.Response(200, json={"results": [resultado(1)]})
        return httpx.Response(200, json={"results": [resultado(1), resultado(2), resultado(3)]})
    falso_searxng(monkeypatch, h)
    txt = asyncio.run(tools.ejecutar("noticias", {"tema": "jaén"}, "usuario"))
    assert txt.count("https://") == 3


def test_prompt_nube_incluye_fecha_actual():
    from aria import config
    assert "Hoy es " in config.system_prompt(True) and "Hoy es " not in config.system_prompt(False)
