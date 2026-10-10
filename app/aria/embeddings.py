"""Embeddings locales de Ollama para la memoria a largo plazo."""
import asyncio
import logging
import time
from array import array
from contextlib import closing

import httpx

from . import config, db

log = logging.getLogger("aria.embeddings")
ESPERA_S = 10 * 60
MANTENER = "30m"   # el modelo (≈560 MB) se queda cargado: frío tarda ~3,6 s en la Pi; caliente, ~0,2 s
_fallo_hasta = 0.0
_calentando: set = set()


async def vectores(textos: list[str], espera: float = 30, castigar_lentitud: bool = True) -> list[list[float]] | None:
    """Pide vectores al Ollama local. Un error desactiva los intentos diez minutos; quedarse sin tiempo, solo si
    `castigar_lentitud` (el chat espera poco y no castiga: el modelo puede estar cargándose)."""
    global _fallo_hasta
    modelo = config.EMBEDDINGS
    if not modelo or not textos or time.monotonic() < _fallo_hasta:
        return None
    try:
        async with httpx.AsyncClient(timeout=espera) as cliente:
            r = await cliente.post(config.OLLAMA_URL.rstrip("/") + "/api/embed",
                                   json={"model": modelo, "input": textos, "keep_alive": MANTENER})
            r.raise_for_status()
            datos = r.json().get("embeddings")
            if not isinstance(datos, list) or len(datos) != len(textos) or any(not isinstance(v, list) for v in datos):
                raise ValueError("Respuesta de embeddings no válida")
            return [[float(x) for x in v] for v in datos]
    except httpx.TimeoutException:
        if castigar_lentitud:
            _fallo_hasta = time.monotonic() + ESPERA_S
        return None
    except Exception:  # noqa: BLE001 - Ollama puede fallar por red, modelo o respuesta
        _fallo_hasta = time.monotonic() + ESPERA_S
        log.warning("No se pudo obtener el modelo local de embeddings; se reintentará más tarde")
        return None


def calentar() -> None:
    """Carga el modelo en segundo plano (tras una consulta del chat que no pudo esperar)."""
    if _calentando or not config.EMBEDDINGS:
        return
    try:
        t = asyncio.get_running_loop().create_task(vectores(["hola"], espera=60, castigar_lentitud=False))
    except RuntimeError:
        return
    _calentando.add(t)
    t.add_done_callback(_calentando.discard)


def coseno(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    norma_a = sum(x * x for x in a) ** 0.5
    norma_b = sum(x * x for x in b) ** 0.5
    return sum(x * y for x, y in zip(a, b)) / (norma_a * norma_b) if norma_a and norma_b else 0.0


def _guardar(rid: int, modelo: str, vector: list[float]) -> None:
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO memoria_vectores (recuerdo_id, modelo, vector) VALUES (?,?,?) "
                    "ON CONFLICT(recuerdo_id) DO UPDATE SET modelo=excluded.modelo, vector=excluded.vector",
                    (rid, modelo, array("f", vector).tobytes()))


async def indexar(uid: int, rid: int, texto: str) -> None:
    if not config.EMBEDDINGS:
        return
    vs = await vectores([texto])
    if vs:
        await asyncio.to_thread(_guardar, rid, config.EMBEDDINGS, vs[0])


def programar(uid: int, rid: int, texto: str) -> asyncio.Task | None:
    """Indexa un recuerdo sin hacer esperar a la petición que lo creó o editó."""
    try:
        tarea = asyncio.get_running_loop().create_task(indexar(uid, rid, texto))
    except RuntimeError:
        return None
    tarea.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
    return tarea


async def rellenar(uid: int | None = None, max: int = 50) -> int:
    """Calcula los vectores ausentes o de un modelo anterior."""
    if not config.EMBEDDINGS or max <= 0:
        return 0
    with closing(db._con()) as con:
        sql = ("SELECT r.id, r.texto FROM recuerdos r LEFT JOIN memoria_vectores v ON v.recuerdo_id=r.id "
               "WHERE (v.recuerdo_id IS NULL OR v.modelo<>?)")
        params = [config.EMBEDDINGS]
        if uid is not None:
            sql += " AND r.user_id=?"
            params.append(uid)
        sql += " ORDER BY r.id LIMIT ?"
        params.append(max)
        filas = con.execute(sql, params).fetchall()
    vs = await vectores([r["texto"] for r in filas])
    if not vs:
        return 0
    for r, vector in zip(filas, vs):
        await asyncio.to_thread(_guardar, r["id"], config.EMBEDDINGS, vector)
    return len(vs)
