"""Búsqueda en internet a través de SearXNG (contenedor interno `aria-searxng`).

`buscar()` devuelve resultados limpios (título, url, extracto, fecha) y `formatear()` los
convierte en un texto compacto para el modelo. Nada de esto sale por la red salvo la
llamada a SearXNG: ARIA nunca habla directamente con los buscadores."""
import html
import os
import re
import time
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

URL = os.environ.get("SEARXNG_URL", "http://searxng:8080").rstrip("/")
TIMEOUT_S = 8.0
CACHE_S = 10 * 60
CACHE_MAX = 64
MAX_CONSULTA = 200
MAX_TITULO = 100
MAX_EXTRACTO = 220
MAX_RESULTADO = 1500   # caracteres que recibe el modelo como máximo
IDIOMA = "es-ES"

_cache: dict = {}      # (consulta, categoria, rango, n) -> (instante, resultados)
_ahora = time.monotonic  # sustituible en las pruebas

_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|dclid|msclkid|yclid|mc_cid|mc_eid|igshid|ref|ref_src|"
                       r"cmpid|ocid|_ga|_gl|spm|share|source)$", re.I)
_ETIQUETAS = re.compile(r"<[^>]*>")
_ESPACIOS = re.compile(r"\s+")
# Escrituras que no son el español: se descartan salvo que la propia consulta las use.
_AJENA = re.compile("[\u0400-\u052f\u0590-\u06ff\u0e00-\u0e7f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


class BusquedaError(Exception):
    """Fallo de búsqueda. El mensaje está en español y se puede mostrar tal cual."""


def limpiar_texto(t, maximo: int) -> str:
    """Quita HTML y entidades, colapsa espacios y recorta en una palabra entera."""
    t = html.unescape(_ETIQUETAS.sub(" ", str(t or "")))
    t = _ESPACIOS.sub(" ", t).strip()
    if len(t) <= maximo:
        return t
    corte = t[:maximo - 1].rsplit(" ", 1)[0] if " " in t[:maximo - 1] else t[:maximo - 1]
    return corte.rstrip(" ,;:.-–—") + "…"


def limpiar_url(u) -> str | None:
    """Solo http/https, sin credenciales, sin fragmento y sin parámetros de seguimiento."""
    try:
        p = urlsplit(str(u or "").strip())
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        return None
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k)]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def dominio(u: str) -> str:
    h = (urlsplit(u).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _fecha(v) -> str | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        m = re.match(r"\d{4}-\d{2}-\d{2}", str(v))
        return m.group(0) if m else None


def procesar(datos: dict, n: int, consulta: str = "") -> list:
    """JSON de SearXNG -> hasta `n` resultados, uno por dominio."""
    ajena_ok = bool(_AJENA.search(consulta))
    vistos, out = set(), []
    for r in (datos.get("results") or []) if isinstance(datos, dict) else []:
        if not isinstance(r, dict):
            continue
        url = limpiar_url(r.get("url"))
        titulo = limpiar_texto(r.get("title"), MAX_TITULO)
        if not url or not titulo or (not ajena_ok and _AJENA.search(titulo)):
            continue
        dom = dominio(url)
        if dom in vistos:
            continue
        vistos.add(dom)
        out.append({"titulo": titulo, "url": url, "dominio": dom,
                    "extracto": limpiar_texto(r.get("content"), MAX_EXTRACTO),
                    "fecha": _fecha(r.get("publishedDate"))})
        if len(out) >= n:
            break
    return out


async def buscar(consulta: str, categoria: str = "general", n: int = 5, rango: str | None = None) -> list:
    """Busca en internet. categoria: 'general' | 'news'. rango: None | 'day' | 'week' | 'month'.

    Lanza BusquedaError (mensaje en español) si no se puede buscar."""
    consulta = " ".join(str(consulta or "").split())[:MAX_CONSULTA]
    if not consulta:
        raise BusquedaError("Dime qué quieres buscar.")
    categoria = "news" if categoria == "news" else "general"
    n = max(1, min(int(n), 10))
    clave = (consulta.lower(), categoria, rango, n)
    c = _cache.get(clave)
    if c and _ahora() - c[0] < CACHE_S:
        return c[1]
    params = {"q": consulta, "format": "json", "language": IDIOMA, "categories": categoria, "safesearch": 1}
    if rango in ("day", "week", "month"):
        params["time_range"] = rango
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S, connect=3.0)) as cl:
            r = await cl.get(f"{URL}/search", params=params)
        if r.status_code != 200:
            raise BusquedaError("El servicio de búsqueda no está disponible ahora mismo.")
        datos = r.json()
    except httpx.TimeoutException as e:
        raise BusquedaError("La búsqueda ha tardado demasiado; inténtalo de nuevo en un momento.") from e
    except (httpx.HTTPError, ValueError) as e:
        raise BusquedaError("No puedo buscar en internet ahora mismo.") from e
    res = procesar(datos, n, consulta)
    if len(_cache) >= CACHE_MAX:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:CACHE_MAX // 2]:
            _cache.pop(k, None)
    if res:  # no se cachean las búsquedas vacías: puede ser un fallo pasajero de los motores
        _cache[clave] = (_ahora(), res)
    return res


def formatear(consulta: str, resultados: list, maximo: int = MAX_RESULTADO) -> str:
    """Texto compacto (<= maximo caracteres) para el modelo. Cada URL va en su propia línea."""
    if not resultados:
        return f"No he encontrado resultados en internet para «{limpiar_texto(consulta, 80)}»."
    cab = f"Resultados de internet para «{limpiar_texto(consulta, 80)}» (cita las fuentes con sus enlaces):"
    for res in range(len(resultados), 0, -1):
        for lim in range(MAX_EXTRACTO, -1, -20):
            lineas = [cab]
            for i, r in enumerate(resultados[:res], 1):
                meta = r["dominio"] + (f", {r['fecha']}" if r["fecha"] else "")
                ext = limpiar_texto(r["extracto"], lim) if lim else ""
                lineas.append(f"{i}. {r['titulo']} ({meta})" + (f": {ext}" if ext else ""))
                lineas.append(f"   {r['url']}")
            txt = "\n".join(lineas)
            if len(txt) <= maximo:
                return txt
    return txt[:maximo]
