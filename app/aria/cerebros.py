"""Cadena de cerebros: varios proveedores de IA gratuitos probados en orden.

Cada proveedor sabe generar UNA ronda del bucle de chat (texto en streaming y,
si hace falta, llamadas a herramientas). Si falla (cuota, clave, tiempo...) el
bucle de chat pasa al siguiente. Los mensajes se guardan siempre en formato
Ollama; los proveedores compatibles con OpenAI los convierten con las funciones
de este módulo.

Para añadir un proveedor nuevo: ver SKILLS.md.
"""
import json
import os
import re
import time
from typing import AsyncIterator

import httpx

from . import config, tools

CONEXION_S = 5          # tiempo máximo para conectar
PRIMER_TOKEN_NUBE_S = 30  # sin datos durante este tiempo => se considera caído
ESPERA_CUOTA_S = 15 * 60
ESPERA_CLAVE_S = 30 * 60
ESPERA_RED_S = 60
ESPERA_OTRO_S = 30
ESPERA_MAX_S = 6 * 3600
ESPERA_MIN_S = 5

_ahora = time.time  # sustituible en las pruebas


class ProveedorError(Exception):
    """Fallo de un proveedor. tipo: cuota | clave | modelo | timeout | red | http."""

    def __init__(self, tipo: str, mensaje: str = "", espera: float | None = None):
        super().__init__(mensaje or tipo)
        self.tipo, self.mensaje, self.espera = tipo, mensaje or tipo, espera


# --- Errores HTTP -> ProveedorError ---------------------------------------------------------
def _segundos_reintento(cabeceras, cuerpo: str) -> float | None:
    v = (cabeceras or {}).get("retry-after")
    if v:
        try:
            return float(v)
        except ValueError:
            pass
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', cuerpo or "")
    return float(m.group(1)) if m else None


def clasificar_http(estado: int, cabeceras=None, cuerpo: str = "") -> ProveedorError:
    t = (cuerpo or "").lower()
    if estado == 429 or (estado >= 400 and re.search(r"rate.?limit|quota|usage limit|too many requests", t)):
        return ProveedorError("cuota", "límite de uso alcanzado", _segundos_reintento(cabeceras, cuerpo))
    if estado in (401, 403):
        return ProveedorError("clave", "clave o sesión rechazada")
    if estado == 404:
        return ProveedorError("modelo", "modelo no disponible")
    if estado in (408, 504):
        return ProveedorError("timeout", "tiempo de espera agotado")
    if estado >= 500:
        return ProveedorError("red", f"el servicio devolvió {estado}")
    return ProveedorError("http", f"error {estado}")


def _error_httpx(e: Exception) -> ProveedorError:
    if isinstance(e, httpx.TimeoutException):
        return ProveedorError("timeout", "tiempo de espera agotado")
    return ProveedorError("red", "sin conexión")


# --- Conversión de formato Ollama <-> OpenAI -------------------------------------------------
def herramientas_openai(specs: list) -> list:
    """Mismo esquema JSON; solo se quita 'parameters' si no tiene propiedades (Gemini lo prefiere)."""
    out = []
    for s in specs:
        f = dict(s["function"])
        if not (f.get("parameters") or {}).get("properties"):
            f.pop("parameters", None)
        out.append({"type": "function", "function": f})
    return out


def a_openai(msgs: list) -> list:
    """Mensajes en formato Ollama -> formato OpenAI (tool_calls con id, argumentos como cadena JSON)."""
    out, pendientes = [], []
    for n, m in enumerate(msgs):
        rol = m.get("role")
        if rol == "assistant" and m.get("tool_calls"):
            llamadas, pendientes = [], []
            for i, ll in enumerate(m["tool_calls"]):
                f = ll.get("function", {})
                args = f.get("arguments") or {}
                cid = ll.get("id") or f"call_{n}_{i}"
                pendientes.append((cid, f.get("name", "")))
                llamadas.append({"id": cid, "type": "function", "function": {
                    "name": f.get("name", ""),
                    "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}})
            out.append({"role": "assistant", "content": m.get("content") or None, "tool_calls": llamadas})
        elif rol == "tool":
            nombre = m.get("tool_name", "")
            idx = next((i for i, (_, nom) in enumerate(pendientes) if nom == nombre), 0 if pendientes else None)
            cid = pendientes.pop(idx)[0] if idx is not None else f"call_{n}_0"
            out.append({"role": "tool", "tool_call_id": cid, "content": str(m.get("content", ""))})
        else:
            out.append({"role": rol, "content": m.get("content", "")})
    return out


class AcumuladorLlamadas:
    """Junta los fragmentos de tool_calls de un stream OpenAI (por índice) y los devuelve en formato Ollama."""

    def __init__(self):
        self._huecos: dict = {}
        self._por_id: dict = {}

    def anadir(self, deltas) -> None:
        for d in deltas or []:
            idx, cid = d.get("index"), d.get("id")
            if idx is None:  # Gemini a veces omite el índice
                if cid:
                    idx = self._por_id.get(cid, len(self._huecos))
                else:
                    idx = max(self._huecos, default=0)
            h = self._huecos.setdefault(idx, {"id": None, "name": "", "args": ""})
            if d.get("id"):
                h["id"] = d["id"]
                self._por_id[d["id"]] = idx
            f = d.get("function") or {}
            if f.get("name"):
                h["name"] += f["name"] if h["name"] != f["name"] else ""
            if f.get("arguments"):
                h["args"] += f["arguments"]

    def resultado(self) -> list:
        out = []
        for idx in sorted(self._huecos):
            h = self._huecos[idx]
            if not h["name"]:
                continue
            try:
                args = json.loads(h["args"]) if h["args"].strip() else {}
            except ValueError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            ll = {"function": {"name": h["name"], "arguments": args}}
            if h["id"]:
                ll["id"] = h["id"]
            out.append(ll)
        return out


# --- Proveedores ------------------------------------------------------------------------------
def _ultimo_usuario(msgs: list) -> str:
    return next((m.get("content", "") for m in reversed(msgs) if m.get("role") == "user"), "")


class Proveedor:
    id = ""
    nombre = ""
    nube = True            # las nubes reciben TODAS las herramientas; el local solo las relevantes
    var_clave: str | None = None
    var_modelo: str | None = None
    modelo_defecto = ""
    ayuda = ""

    def modelo(self) -> str:
        return (os.environ.get(self.var_modelo, "") if self.var_modelo else "").strip() or self.modelo_defecto

    def tiene_clave(self) -> bool:
        return True if not self.var_clave else bool(os.environ.get(self.var_clave, "").strip())

    def etiqueta(self) -> str:
        m = self.modelo()
        return f"{self.nombre} · {m[:-6] if m.endswith('-cloud') else m}"

    async def ronda(self, msgs: list, con_tools: bool = True) -> AsyncIterator[dict]:
        """Eventos: {"type": "token"|"pensando"|"llamadas"|"aviso", ...}. Lanza ProveedorError."""
        raise NotImplementedError
        yield  # pragma: no cover


# Los modelos locales que han rechazado tools (se recuerda para no reintentar).
_sin_tools: set = set()


class OllamaNativo(Proveedor):
    """/api/chat de Ollama: el modelo local y Ollama Cloud (modelos *-cloud) usan la misma API."""

    def __init__(self, id, nombre, nube, var_modelo=None, modelo_defecto="", ayuda=""):
        self.id, self.nombre, self.nube = id, nombre, nube
        self.var_modelo, self.modelo_defecto, self.ayuda = var_modelo, modelo_defecto, ayuda

    def modelo(self) -> str:
        return super().modelo() if self.nube else config.modelo_activo()

    async def _stream(self, cliente, cuerpo):
        async with cliente.stream("POST", f"{config.OLLAMA_URL}/api/chat", json=cuerpo) as r:
            if r.status_code != 200:
                yield {"_http": r.status_code, "_texto": (await r.aread()).decode("utf-8", "replace"),
                       "_cab": dict(r.headers)}
                return
            async for linea in r.aiter_lines():
                if linea.strip():
                    try:
                        yield json.loads(linea)
                    except ValueError:
                        continue

    async def ronda(self, msgs, con_tools=True):
        modelo = self.modelo()
        base = [{"role": "system", "content": config.system_prompt(self.nube)}] + msgs
        if self.nube:
            pedidas = set(tools._REGISTRO) if con_tools else set()
        else:  # local: solo las herramientas cuyas palabras clave aparecen en el mensaje
            pedidas = tools.relevantes(_ultimo_usuario(msgs)) if con_tools else set()
        usar_tools = modelo not in _sin_tools and bool(pedidas)
        timeout = (httpx.Timeout(PRIMER_TOKEN_NUBE_S, connect=CONEXION_S) if self.nube
                   else httpx.Timeout(600, connect=10))
        try:
            async with httpx.AsyncClient(timeout=timeout) as cliente:
                for intento in (0, 1):
                    cuerpo = {"model": modelo, "messages": base, "stream": True}
                    if not self.nube:
                        cuerpo["keep_alive"] = config.KEEP_ALIVE
                        cuerpo["options"] = {"num_ctx": config.NUM_CTX}
                    if usar_tools:
                        cuerpo["tools"] = tools.especificaciones(pedidas)
                    texto, llamadas, modo, fallo, pensando = "", [], None, None, False
                    async for ch in self._stream(cliente, cuerpo):
                        if "_http" in ch:
                            fallo = ch
                            break
                        if ch.get("error"):
                            raise clasificar_http(500, None, str(ch["error"]))
                        m = ch.get("message") or {}
                        if m.get("thinking") and not pensando and not texto:
                            pensando = True
                            yield {"type": "pensando"}
                        if m.get("content"):
                            texto += m["content"]
                            if self.nube:
                                yield {"type": "token", "text": m["content"]}
                            elif modo is None and texto.strip():
                                modo = "json" if usar_tools and texto.lstrip()[0] == "{" else "texto"
                                if modo == "texto":
                                    yield {"type": "token", "text": texto}
                            elif modo == "texto":
                                yield {"type": "token", "text": m["content"]}
                        llamadas += m.get("tool_calls") or []
                    if fallo:
                        if fallo["_http"] == 400 and "tools" in fallo["_texto"] and usar_tools and not self.nube:
                            _sin_tools.add(modelo)
                            usar_tools = False
                            yield {"type": "aviso", "text": "Este modelo no admite herramientas; respondo sin ellas."}
                            continue
                        if fallo["_http"] == 404 and not self.nube:
                            raise ProveedorError("modelo", f"El modelo '{modelo}' no está instalado. "
                                                 "Descárgalo en Ajustes → Modelos.")
                        raise clasificar_http(fallo["_http"], fallo["_cab"], fallo["_texto"])
                    if not llamadas and modo == "json":
                        rescatada = tools.rescatar_llamada(texto, pedidas)
                        if rescatada:
                            llamadas, texto = [rescatada], ""
                        else:
                            yield {"type": "token", "text": texto}
                    if llamadas:
                        yield {"type": "llamadas", "texto": texto, "llamadas": llamadas}
                    return
        except httpx.HTTPError as e:
            raise _error_httpx(e) from e


class OpenAICompatible(Proveedor):
    """Chat completions compatible con OpenAI con streaming SSE (Groq, Gemini...)."""

    def __init__(self, id, nombre, url, var_clave, var_modelo, modelo_defecto, ayuda=""):
        self.id, self.nombre, self.url = id, nombre, url
        self.var_clave, self.var_modelo, self.modelo_defecto, self.ayuda = var_clave, var_modelo, modelo_defecto, ayuda

    async def ronda(self, msgs, con_tools=True):
        clave = os.environ.get(self.var_clave, "").strip()
        if not clave:
            raise ProveedorError("clave", "falta la clave")
        cuerpo = {"model": self.modelo(), "stream": True,
                  "messages": [{"role": "system", "content": config.system_prompt(True)}] + a_openai(msgs)}
        if con_tools:
            cuerpo["tools"] = herramientas_openai(tools.especificaciones())
        acum = AcumuladorLlamadas()
        texto = ""
        timeout = httpx.Timeout(PRIMER_TOKEN_NUBE_S, connect=CONEXION_S)
        try:
            async with httpx.AsyncClient(timeout=timeout) as cliente:
                async with cliente.stream("POST", self.url, json=cuerpo,
                                          headers={"Authorization": f"Bearer {clave}"}) as r:
                    if r.status_code != 200:
                        raise clasificar_http(r.status_code, dict(r.headers),
                                              (await r.aread()).decode("utf-8", "replace")[:2000])
                    async for linea in r.aiter_lines():
                        if not linea.startswith("data:"):
                            continue
                        dato = linea[5:].strip()
                        if dato == "[DONE]":
                            break
                        try:
                            ch = json.loads(dato)
                        except ValueError:
                            continue
                        if isinstance(ch, dict) and ch.get("error"):
                            raise clasificar_http(500, None, json.dumps(ch["error"]))
                        for opcion in (ch.get("choices") or []) if isinstance(ch, dict) else []:
                            d = opcion.get("delta") or {}
                            if d.get("content"):
                                texto += d["content"]
                                yield {"type": "token", "text": d["content"]}
                            acum.anadir(d.get("tool_calls"))
        except httpx.HTTPError as e:
            raise _error_httpx(e) from e
        llamadas = acum.resultado()
        if llamadas:
            yield {"type": "llamadas", "texto": texto, "llamadas": llamadas}


PROVEEDORES = {p.id: p for p in (
    OllamaNativo("ollama_cloud", "Ollama Cloud", True, "ARIA_MODELO_OLLAMA_CLOUD", "gpt-oss:120b-cloud",
                 "Usa tu cuenta de Ollama: docker exec -it aria-ollama ollama signin"),
    OpenAICompatible("groq", "Groq", "https://api.groq.com/openai/v1/chat/completions",
                     "GROQ_API_KEY", "ARIA_MODELO_GROQ", "llama-3.3-70b-versatile"),
    OpenAICompatible("gemini", "Google Gemini",
                     "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                     "GEMINI_API_KEY", "ARIA_MODELO_GEMINI", "gemini-2.5-flash"),
    OllamaNativo("local", "Local", False, ayuda="Modelo local de Ollama; funciona sin conexión"),
)}
ORDEN_DEFECTO = ["ollama_cloud", "groq", "gemini", "local"]


# --- Orden, activación y esperas ----------------------------------------------------------------
def _ruta():
    return config.DATA_DIR / "cerebros.json"


def _orden_env() -> list:
    ids = [x.strip().lower() for x in os.environ.get("ARIA_CEREBROS", "").split(",")]
    ids = [i for i in dict.fromkeys(ids) if i in PROVEEDORES]
    return ids or list(ORDEN_DEFECTO)


def configuracion() -> tuple[list, set]:
    """(orden completo, ids desactivados). data/cerebros.json manda sobre ARIA_CEREBROS."""
    try:
        d = json.loads(_ruta().read_text())
        orden = [i for i in d.get("orden", []) if i in PROVEEDORES]
        apagados = {i for i in d.get("desactivados", []) if i in PROVEEDORES and i != "local"}
    except (OSError, ValueError, AttributeError):
        orden, apagados = _orden_env(), set()
        apagados = {i for i in PROVEEDORES if i not in orden and i != "local"}
    orden = list(dict.fromkeys(orden))
    orden += [i for i in PROVEEDORES if i not in orden]
    return orden, apagados


def guardar(orden: list, desactivados: list) -> None:
    orden = [i for i in dict.fromkeys(orden) if i in PROVEEDORES]
    orden += [i for i in PROVEEDORES if i not in orden]
    datos = {"orden": orden, "desactivados": [i for i in desactivados if i in PROVEEDORES and i != "local"]}
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _ruta().with_suffix(".tmp")
    tmp.write_text(json.dumps(datos))
    tmp.replace(_ruta())


_esperas: dict = {}  # id -> (hasta, tipo)


def en_espera(pid: str):
    e = _esperas.get(pid)
    if e and e[0] > _ahora():
        return e
    _esperas.pop(pid, None)
    return None


def registrar_fallo(pid: str, err: ProveedorError) -> float:
    """Anota el fallo y devuelve cuántos segundos se salta el proveedor."""
    if err.tipo == "cuota":
        s = min(max(err.espera, ESPERA_MIN_S), ESPERA_MAX_S) if err.espera else ESPERA_CUOTA_S
    elif err.tipo in ("clave", "modelo"):
        s = ESPERA_CLAVE_S
    elif err.tipo in ("timeout", "red"):
        s = ESPERA_RED_S
    else:
        s = ESPERA_OTRO_S
    _esperas[pid] = (_ahora() + s, err.tipo)
    return s


def limpiar_espera(pid: str) -> None:
    _esperas.pop(pid, None)


def cadena() -> list:
    """Proveedores a probar, en orden: activados, con clave y sin espera. El local siempre cierra la cadena."""
    orden, apagados = configuracion()
    out = [PROVEEDORES[i] for i in orden
           if i != "local" and i not in apagados and PROVEEDORES[i].tiene_clave() and not en_espera(i)]
    # El local respeta su posición en el orden (puede ir primero si Lucía lo prefiere).
    pos = orden.index("local")
    antes = sum(1 for i in orden[:pos] if PROVEEDORES[i] in out)
    out.insert(antes, PROVEEDORES["local"])
    return out


def estado() -> list:
    orden, apagados = configuracion()
    primero = cadena()[0].id
    out = []
    for i in orden:
        p = PROVEEDORES[i]
        e = en_espera(i)
        if not p.tiene_clave():
            st, det = "sin_clave", "falta la clave"
        elif e and e[1] == "cuota":
            st, det = "espera", "en espera hasta las " + time.strftime("%H:%M", time.localtime(e[0])) + " por límite de uso"
        elif e and e[1] in ("clave", "modelo"):
            st, det = "clave_invalida", "clave o sesión rechazada" if e[1] == "clave" else "modelo no disponible"
        elif e:
            st, det = "sin_conexion", "sin conexión"
        else:
            st, det = "configurado", "configurado"
        out.append({"id": i, "nombre": p.nombre, "modelo": p.modelo(), "etiqueta": p.etiqueta(),
                    "activo": i not in apagados, "estado": st, "detalle": det,
                    "hasta": e[0] if e else None, "nube": p.nube, "primero": i == primero,
                    "clave_var": p.var_clave, "modelo_var": p.var_modelo, "ayuda": p.ayuda,
                    "bloqueado": i == "local"})
    return out


async def probar(pid: str) -> dict:
    """Envía una pregunta de una línea y mide la latencia (sin herramientas)."""
    p = PROVEEDORES[pid]
    if not p.tiene_clave():
        return {"ok": False, "error": "Falta la clave (" + (p.var_clave or "") + ")."}
    t0, ttft, texto = time.perf_counter(), None, ""
    try:
        async for ev in p.ronda([{"role": "user", "content": "Responde solo con la palabra: OK"}], con_tools=False):
            if ev["type"] == "token":
                if ttft is None:
                    ttft = time.perf_counter() - t0
                texto += ev["text"]
    except ProveedorError as e:
        if pid != "local":
            registrar_fallo(pid, e)
        return {"ok": False, "error": e.mensaje[:200], "tipo": e.tipo}
    limpiar_espera(pid)
    total = time.perf_counter() - t0
    return {"ok": True, "ms": int(total * 1000), "primer_token_ms": int((ttft or total) * 1000),
            "texto": texto.strip()[:80]}
