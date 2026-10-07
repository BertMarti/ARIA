import asyncio
import json

import pytest

from aria import cerebros, chat, config, tools
from aria.cerebros import AcumuladorLlamadas, ProveedorError, a_openai, clasificar_http


@pytest.fixture(autouse=True)
def limpio(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    cerebros._esperas.clear()
    for v in ("GROQ_API_KEY", "GEMINI_API_KEY", "ARIA_CEREBROS"):
        monkeypatch.delenv(v, raising=False)
    yield
    cerebros._esperas.clear()


def correr(gen):
    async def todo():
        return [e async for e in gen]
    return asyncio.run(todo())


# --- Adaptador OpenAI ---------------------------------------------------------------------
def test_fragmentos_de_tool_calls_se_juntan_por_indice():
    a = AcumuladorLlamadas()
    a.anadir([{"index": 0, "id": "c1", "function": {"name": "buscar_en_netflix", "arguments": ""}}])
    a.anadir([{"index": 1, "id": "c2", "function": {"name": "fecha_hora", "arguments": "{}"}}])
    a.anadir([{"index": 0, "function": {"arguments": '{"titulo": "Do'}}])
    a.anadir([{"index": 0, "function": {"arguments": 'ra"}'}}])
    r = a.resultado()
    assert r[0]["function"] == {"name": "buscar_en_netflix", "arguments": {"titulo": "Dora"}}
    assert r[1]["function"] == {"name": "fecha_hora", "arguments": {}}
    assert r[0]["id"] == "c1"


def test_fragmentos_sin_indice_estilo_gemini():
    a = AcumuladorLlamadas()
    a.anadir([{"id": "a", "function": {"name": "fecha_hora", "arguments": "{}"}}])
    a.anadir([{"id": "b", "function": {"name": "estado_sistema", "arguments": "{}"}}])
    assert [x["function"]["name"] for x in a.resultado()] == ["fecha_hora", "estado_sistema"]


def test_argumentos_invalidos_dan_dict_vacio():
    a = AcumuladorLlamadas()
    a.anadir([{"index": 0, "id": "c", "function": {"name": "fecha_hora", "arguments": "{roto"}}])
    assert a.resultado()[0]["function"]["arguments"] == {}


def test_mensajes_ollama_a_openai_con_resultados_de_herramienta():
    msgs = [
        {"role": "user", "content": "temperatura"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "estado_sistema", "arguments": {}}},
            {"function": {"name": "buscar_en_netflix", "arguments": {"titulo": "Ñu"}}}]},
        {"role": "tool", "tool_name": "buscar_en_netflix", "content": "enlace"},
        {"role": "tool", "tool_name": "estado_sistema", "content": "50 °C"},
    ]
    o = a_openai(msgs)
    ll = o[1]["tool_calls"]
    assert o[1]["content"] is None and ll[0]["type"] == "function"
    assert json.loads(ll[1]["function"]["arguments"]) == {"titulo": "Ñu"}
    assert o[2] == {"role": "tool", "tool_call_id": ll[1]["id"], "content": "enlace"}
    assert o[3]["tool_call_id"] == ll[0]["id"]
    assert ll[0]["id"] != ll[1]["id"]


def test_herramientas_openai_mismo_esquema_y_sin_parametros_vacios():
    esp = cerebros.herramientas_openai(tools.especificaciones())
    por = {e["function"]["name"]: e["function"] for e in esp}
    assert "parameters" not in por["fecha_hora"]
    assert por["buscar_en_netflix"]["parameters"]["required"] == ["titulo"]
    assert "borrar_dispositivo_vpn" not in por  # el borrado de VPN es solo de la interfaz


# --- Clasificación de errores y esperas -----------------------------------------------------
def test_clasificar_http():
    assert clasificar_http(429, {"retry-after": "42"}).espera == 42
    assert clasificar_http(401).tipo == "clave"
    assert clasificar_http(403).tipo == "clave"
    assert clasificar_http(500, None, "you have reached your usage limit").tipo == "cuota"
    assert clasificar_http(503).tipo == "red"
    assert clasificar_http(429, {}, '{"retryDelay": "34s"}').espera == 34


def test_espera_por_cuota_y_retry_after(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(cerebros, "_ahora", lambda: t[0])
    assert cerebros.registrar_fallo("groq", ProveedorError("cuota")) == 15 * 60
    assert cerebros.en_espera("groq")
    t[0] += 15 * 60 + 1
    assert cerebros.en_espera("groq") is None
    assert cerebros.registrar_fallo("groq", ProveedorError("cuota", espera=90)) == 90
    assert cerebros.registrar_fallo("groq", ProveedorError("cuota", espera=10 ** 6)) == cerebros.ESPERA_MAX_S


def test_sin_clave_se_omite_y_espera_se_salta(monkeypatch):
    assert [p.id for p in cerebros.cadena()] == ["ollama_cloud", "local"]
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "SECRETO-GROQ-123")
    assert [p.id for p in cerebros.cadena()] == ["ollama_cloud", "groq", "gemini", "local"]
    cerebros.registrar_fallo("groq", ProveedorError("cuota"))
    assert [p.id for p in cerebros.cadena()] == ["ollama_cloud", "gemini", "local"]
    est = {e["id"]: e for e in cerebros.estado()}
    assert est["groq"]["estado"] == "espera" and "hasta las" in est["groq"]["detalle"]
    assert "SECRETO" not in json.dumps(est)  # ninguna clave en el estado


def test_orden_y_desactivacion_persisten_y_local_no_se_apaga(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    cerebros.guardar(["gemini", "local", "ollama_cloud", "groq"], ["ollama_cloud", "local"])
    assert [p.id for p in cerebros.cadena()] == ["gemini", "local"]
    orden, apagados = cerebros.configuracion()
    assert orden[0] == "gemini" and apagados == {"ollama_cloud"}


def test_orden_desde_env(monkeypatch):
    monkeypatch.setenv("ARIA_CEREBROS", "local,ollama_cloud")
    assert [p.id for p in cerebros.cadena()] == ["local"] + (["ollama_cloud"])


# --- Cadena con proveedores falsos ---------------------------------------------------------------
class Falso(cerebros.Proveedor):
    def __init__(self, id, eventos=None, error=None, tras=0):
        self.id, self.nombre, self.eventos, self.error, self.tras = id, id, eventos or [], error, tras
        self.llamado = 0

    def modelo(self):
        return "m"

    async def ronda(self, msgs, con_tools=True, **_):
        self.llamado += 1
        for i, ev in enumerate(self.eventos):
            if self.error and i == self.tras:
                raise self.error
            yield ev
        if self.error and self.tras >= len(self.eventos):
            raise self.error


def tok(t):
    return {"type": "token", "text": t}


@pytest.mark.parametrize("err", [ProveedorError("cuota"), ProveedorError("timeout"), ProveedorError("clave")])
def test_cae_al_siguiente_en_silencio(monkeypatch, err):
    a, b = Falso("a", error=err), Falso("b", [tok("hola")])
    monkeypatch.setattr(cerebros, "cadena", lambda: [a, b])
    evs = correr(chat.responder([{"role": "user", "content": "hola"}]))
    tipos = [e["type"] for e in evs]
    assert tipos == ["cerebro", "token", "fin"] and evs[0]["id"] == "b"
    assert "aviso" not in tipos
    assert cerebros.en_espera("a")  # recordado para saltarlo


def test_fallo_tras_tokens_avisa_y_reinicia(monkeypatch):
    a = Falso("a", [tok("par")], error=ProveedorError("timeout"), tras=1)
    b = Falso("b", [tok("completa")])
    monkeypatch.setattr(cerebros, "cadena", lambda: [a, b])
    tipos = [e["type"] for e in correr(chat.responder([{"role": "user", "content": "x"}]))]
    assert tipos == ["cerebro", "token", "aviso", "reinicio", "cerebro", "token", "fin"]


def test_todos_fallan_da_error(monkeypatch):
    monkeypatch.setattr(cerebros, "cadena", lambda: [Falso("a", error=ProveedorError("red"))])
    evs = correr(chat.responder([{"role": "user", "content": "x"}]))
    assert evs[-1]["type"] == "error"


def test_llamada_a_herramienta_y_segunda_ronda(monkeypatch):
    llamada = {"function": {"name": "fecha_hora", "arguments": {}}}
    vistos = []

    class P(Falso):
        async def ronda(self, msgs, con_tools=True, **_):
            vistos.append(list(msgs))
            if len(vistos) == 1:
                yield {"type": "llamadas", "texto": "", "llamadas": [llamada]}
            else:
                yield tok("Son las tantas")

    monkeypatch.setattr(cerebros, "cadena", lambda: [P("a")])
    evs = correr(chat.responder([{"role": "user", "content": "qué hora es"}]))
    assert [e["type"] for e in evs] == ["cerebro", "herramienta", "resultado", "cerebro", "token", "fin"]
    assert vistos[1][-1]["role"] == "tool" and vistos[1][-1]["tool_name"] == "fecha_hora"
    assert vistos[1][-2]["tool_calls"] == [llamada]


# --- El filtrado por palabras clave solo afecta al local -------------------------------------------
class _Capturador:
    def __init__(self):
        self.cuerpos = []

    def stream(self, metodo, url, json=None, **kw):
        self.cuerpos.append(json)
        capt = self

        class R:
            status_code = 200

            async def __aenter__(s):
                return s

            async def __aexit__(s, *a):
                return False

            async def aiter_lines(s):
                yield '{"message": {"content": "ok"}, "done": true}'
        return R()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def test_local_filtra_herramientas_y_la_nube_las_recibe_todas(monkeypatch):
    capt = _Capturador()
    monkeypatch.setattr(cerebros.httpx, "AsyncClient", lambda **kw: capt)
    msg = [{"role": "user", "content": "¿Qué temperatura tiene la Raspberry?"}]
    correr(cerebros.PROVEEDORES["local"].ronda(msg))
    correr(cerebros.PROVEEDORES["ollama_cloud"].ronda(msg))
    local, nube = capt.cuerpos
    assert [t["function"]["name"] for t in local["tools"]] == ["estado_sistema"]
    assert {t["function"]["name"] for t in nube["tools"]} == set(tools._REGISTRO)
    assert "options" in local and "options" not in nube
    assert nube["model"].endswith("-cloud")
    # y en una charla el local no recibe ninguna herramienta
    correr(cerebros.PROVEEDORES["local"].ronda([{"role": "user", "content": "Hola"}]))
    assert "tools" not in capt.cuerpos[-1]
    assert "Lucía" in capt.cuerpos[0]["messages"][0]["content"] or not config.NOMBRE_USUARIO


def test_thinking_no_se_muestra_como_respuesta(monkeypatch):
    class C(_Capturador):
        def stream(self, *a, **kw):
            r = super().stream(*a, **kw)

            async def lineas(s):
                yield '{"message": {"thinking": "razono"}}'
                yield '{"message": {"content": "Hola"}, "done": true}'
            type(r).aiter_lines = lineas
            return r
    monkeypatch.setattr(cerebros.httpx, "AsyncClient", lambda **kw: C())
    evs = correr(cerebros.PROVEEDORES["ollama_cloud"].ronda([{"role": "user", "content": "hola"}]))
    assert [e["type"] for e in evs] == ["pensando", "token"]
    assert "razono" not in json.dumps(evs)


def test_openai_sin_clave_lanza_error_de_clave():
    with pytest.raises(ProveedorError) as e:
        correr(cerebros.PROVEEDORES["groq"].ronda([{"role": "user", "content": "x"}]))
    assert e.value.tipo == "clave"


def test_thought_signature_de_gemini_se_devuelve_en_la_siguiente_ronda():
    a = AcumuladorLlamadas()
    a.anadir([{"index": 0, "id": "g1", "extra_content": {"google": {"thought_signature": "abc"}},
               "function": {"name": "fecha_hora", "arguments": "{}"}}])
    ll = a.resultado()
    o = a_openai([{"role": "user", "content": "x"}, {"role": "assistant", "content": "", "tool_calls": ll},
                  {"role": "tool", "tool_name": "fecha_hora", "content": "ok"}])
    assert o[1]["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "abc"}}
    assert o[1]["tool_calls"][0]["id"] == "g1" and o[2]["tool_call_id"] == "g1"
