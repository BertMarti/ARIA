"""API de Finanzas (/api/finanzas/...). Ambos roles; cada usuario solo sus datos (uid de la sesión)."""
import asyncio
import base64
import binascii
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import agentes, finanzas, finanzas_csv

router = APIRouter(prefix="/api/finanzas")


def _uid(request: Request) -> int:
    return request.state.usuario["id"]


def _err(e: Exception, estado: int = 400) -> JSONResponse:
    return JSONResponse({"error": str(e)}, status_code=estado)


async def _json(request: Request) -> dict:
    try:
        d = await request.json()
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _archivo(d: dict) -> bytes:
    b64 = d.get("archivo")
    if not isinstance(b64, str) or not b64:
        raise finanzas_csv.CsvError("Falta el archivo.")
    if len(b64) > finanzas_csv.MAX_BYTES * 4 // 3 + 8:
        raise finanzas_csv.CsvError("El archivo es demasiado grande (máximo 2 MB).")
    try:
        return base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise finanzas_csv.CsvError("Archivo no válido.") from None


@router.get("/resumen")
async def resumen(request: Request, mes: str = ""):
    uid = _uid(request)
    try:
        r = await asyncio.to_thread(finanzas.resumen_mes, uid, mes or None)
    except finanzas.FinanzasError as e:
        return _err(e)
    r["presupuestos"] = await asyncio.to_thread(finanzas.estado_presupuestos, uid, r["mes"])
    r["meses"] = await asyncio.to_thread(finanzas.meses, uid)
    r["categorias_disponibles"] = await asyncio.to_thread(finanzas.categorias, uid)
    return r


@router.get("/movimientos")
async def movimientos(request: Request, mes: str = "", categoria: str = "", texto: str = ""):
    try:
        return {"movimientos": await asyncio.to_thread(
            finanzas.listar, _uid(request), mes or None, categoria or None, texto[:80] or None)}
    except finanzas.FinanzasError as e:
        return _err(e)


@router.post("/movimientos")
async def crear(request: Request):
    d = await _json(request)
    try:
        return {"movimiento": await asyncio.to_thread(
            finanzas.registrar, _uid(request), d.get("fecha"), d.get("concepto"), d.get("importe"),
            d.get("categoria"), d.get("cuenta"))}
    except finanzas.FinanzasError as e:
        return _err(e)


@router.patch("/movimientos/{mid}")
async def editar(mid: int, request: Request):
    d = await _json(request)
    cambios = {k: d[k] for k in ("fecha", "concepto", "importe", "categoria", "cuenta", "aplicar_a_similares") if k in d}
    try:
        return {"movimiento": await asyncio.to_thread(finanzas.actualizar, _uid(request), mid, cambios)}
    except finanzas.FinanzasError as e:
        return _err(e, 404 if "no encontrado" in str(e) else 400)


@router.delete("/movimientos/{mid}")
async def borrar(mid: int, request: Request):
    if not await asyncio.to_thread(finanzas.borrar, _uid(request), mid):
        return _err(Exception("Movimiento no encontrado."), 404)
    return {"ok": True}


@router.post("/presupuestos")
async def presupuesto(request: Request):
    d = await _json(request)
    try:
        return await asyncio.to_thread(finanzas.fijar_presupuesto, _uid(request), d.get("categoria"), d.get("importe", 0))
    except finanzas.FinanzasError as e:
        return _err(e)


@router.get("/reglas")
async def reglas(request: Request):
    return {"reglas": await asyncio.to_thread(finanzas.reglas, _uid(request))}


@router.post("/reglas")
async def crear_regla(request: Request):
    d = await _json(request)
    try:
        return await asyncio.to_thread(finanzas.anadir_regla, _uid(request), d.get("patron", ""), d.get("categoria"))
    except finanzas.FinanzasError as e:
        return _err(e)


@router.delete("/reglas/{rid}")
async def borrar_regla(rid: int, request: Request):
    if not await asyncio.to_thread(finanzas.borrar_regla, _uid(request), rid):
        return _err(Exception("Regla no encontrada."), 404)
    return {"ok": True}


@router.post("/importar/previa")
async def importar_previa(request: Request):
    """Paso 1: detecta formato y columnas y devuelve una muestra para revisar el mapeo."""
    d = await _json(request)
    try:
        info = await asyncio.to_thread(finanzas_csv.leer, _archivo(d))
        ncols = len(info["cabecera"])
        mapeo = d.get("mapeo") if isinstance(d.get("mapeo"), dict) else info["mapeo"]
        try:
            conv = finanzas_csv.convertir(info["filas"], mapeo, ncols)
        except finanzas_csv.CsvError as e:
            conv = {"movimientos": [], "errores": [], "decimal": ",", "aviso": str(e)}
    except finanzas_csv.CsvError as e:
        return _err(e)
    return {"codificacion": info["codificacion"], "separador": info["separador"], "cabecera": info["cabecera"],
            "mapeo": mapeo, "total": info["total"], "crudas": info["filas"][:5],
            "muestra": conv["movimientos"][:8], "validas": len(conv["movimientos"]),
            "errores": len(conv["errores"]), "decimal": conv["decimal"], "aviso": conv.get("aviso")}


@router.post("/importar")
async def importar(request: Request):
    d = await _json(request)
    try:
        info = await asyncio.to_thread(finanzas_csv.leer, _archivo(d))
        conv = finanzas_csv.convertir(info["filas"], d.get("mapeo"), len(info["cabecera"]))
    except finanzas_csv.CsvError as e:
        return _err(e)
    if not conv["movimientos"]:
        return _err(Exception("No hay ninguna fila válida con ese mapeo."))
    r = await asyncio.to_thread(finanzas.importar, _uid(request), conv["movimientos"], d.get("cuenta"))
    r["errores"] = len(conv["errores"])
    return r


@router.post("/sugerir")
async def sugerir(request: Request):
    """Opcional: pide al primer cerebro en la nube una categoría para los conceptos sin categoría.
    Solo salen de casa los conceptos (no importes ni fechas). Nada se aplica sin que el usuario lo acepte."""
    uid = _uid(request)
    conceptos = await asyncio.to_thread(finanzas.sin_categoria, uid, 25)
    if not conceptos:
        return {"sugerencias": []}
    cats = await asyncio.to_thread(finanzas.categorias, uid)
    sistema = ("Clasificas movimientos bancarios españoles. Devuelve SOLO un objeto JSON {\"concepto\": \"categoría\"} "
               "usando exclusivamente estas categorías: " + ", ".join(cats) + ". Si dudas, usa \"Otros\".")
    salida = await agentes.pregunta_nube(sistema, "\n".join(conceptos), timeout=25, maximo=6000)
    if salida is None:
        return _err(Exception("No hay ningún cerebro en la nube disponible ahora mismo."), 503)
    m = re.search(r"\{.*\}", salida, re.S)
    try:
        datos = json.loads(m.group(0)) if m else {}
    except ValueError:
        datos = {}
    validas = {c.lower(): c for c in cats}
    out = [{"concepto": c, "categoria": validas[str(datos[c]).lower()],
             "patron": finanzas._clave_similar(c) or finanzas.normalizar(c)[:60]}
           for c in conceptos if isinstance(datos, dict) and c in datos and str(datos[c]).lower() in validas]
    return {"sugerencias": out}
