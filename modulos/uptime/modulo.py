"""Módulo de ejemplo «Uptime web»: ¿responde una web pública y con qué latencia?

- Herramienta `comprobar_web(url)` (solo lectura, para todos los roles): la usa el chat («¿responde
  https://example.org?», «¿está caída github.com?»).
- Si se define `UPTIME_URLS` (lista separada por comas, máx. 10), un chequeo de avisos las revisa cada
  `UPTIME_INTERVALO_MIN` minutos (5 por defecto) y avisa al administrador si alguna deja de responder
  (tras dos fallos seguidos) y cuando vuelve.
- `GET /api/modulos/uptime/estado` (solo admin): el último resultado de esas URL.

Las peticiones van con la protección anti-SSRF de ARIA (`aria.comprobar_url`): solo webs PÚBLICAS en los puertos
80/443; nunca la red de casa. Para vigilar un servicio de casa usa «salud» en el modulo.json de su módulo.
"""
import re
import time

MAX_URLS = 10
_ultimo: dict = {}   # url -> {"ok", "estado", "ms", "error", "cuando"}


def _normalizar(url: str) -> str:
    url = (url or "").strip().strip("<>«»\"'")
    if url and not re.match(r"https?://", url, re.I):
        url = "https://" + url        # «example.org» -> «https://example.org»
    return url


def _texto(url: str, r: dict) -> str:
    if r["ok"]:
        return f"{url} responde (código {r['estado']}) en {r['ms']} ms."
    return f"{url} responde con el código {r['estado']} (en {r['ms']} ms): parece que tiene problemas."


def registrar(aria):
    @aria.herramienta(
        "comprobar_web",
        "Comprueba si una web pública responde y su latencia (código HTTP y milisegundos). Úsala cuando "
        "pregunten si una página está caída, funciona o responde.",
        {"url": ("string", "Dirección de la web, p. ej. https://example.org o example.org")}, ("url",),
        solo_lectura=True, roles=("admin", "usuario"), agentes=("aria", "redes"),
        intenciones=[
            (r"(https?://|\b[\w-]+\.(com|es|org|net|io|dev|app|eu|info)\b)",
             r"\b(responde\w*|ca[ií]d[ao]s?|funciona\w*|va|anda|en l[ií]nea|online|uptime|latencia|disponible|"
             r"accesible|levantad[ao])\b"),
        ])
    async def comprobar_web(url: str) -> str:
        url = _normalizar(url)
        try:
            r = await aria.comprobar_url(url)
        except aria.Error as e:
            return f"{url} no responde: {e}"
        return _texto(r["url"], r)

    urls = []
    for u in (aria.config("UPTIME_URLS") or "").split(","):
        u = _normalizar(u)
        if u and u not in urls:
            urls.append(u)
    if len(urls) > MAX_URLS:
        aria.log.warning("UPTIME_URLS tiene %d direcciones; solo se vigilan las %d primeras", len(urls), MAX_URLS)
        urls = urls[:MAX_URLS]
    try:
        intervalo = max(1, min(1440, int(aria.config("UPTIME_INTERVALO_MIN", "5"))))
    except ValueError:
        intervalo = 5

    if urls:
        @aria.chequeo("webs", intervalo_min=intervalo, severidad="aviso", confirmaciones=2,
                      texto_ok=lambda clave: f"{clave} vuelve a responder.")
        async def webs():
            problemas = []
            for url in urls:
                try:
                    r = await aria.comprobar_url(url)
                    _ultimo[url] = {**r, "error": "", "cuando": time.time()}
                    if not r["ok"]:
                        problemas.append(aria.Problema(url, _texto(url, r)))
                except aria.Error as e:
                    _ultimo[url] = {"ok": False, "estado": None, "ms": None, "error": str(e), "cuando": time.time()}
                    problemas.append(aria.Problema(url, f"{url} no responde: {e}"))
            return problemas

    r = aria.router()

    @r.get("/estado")
    async def estado():
        return {"urls": urls, "intervalo_min": intervalo,
                "resultados": [{"url": u, **_ultimo[u]} for u in urls if u in _ultimo]}
