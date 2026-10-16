import asyncio
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from . import documentos

router = APIRouter()
_subidas = defaultdict(deque)


def _uid(request):
    return request.state.usuario["id"]


def _limite(uid):
    ahora = time.time()
    cola = _subidas[uid]
    while cola and cola[0] <= ahora - 3600:
        cola.popleft()
    if len(cola) >= 10:
        return False
    cola.append(ahora)
    return True


@router.get("/api/documentos")
async def listar(request: Request):
    return {"documentos": await asyncio.to_thread(documentos.listar, _uid(request))}


@router.post("/api/documentos")
async def subir(request: Request):
    if not _limite(_uid(request)):
        return JSONResponse({"error": "Límite de 10 subidas por hora."}, status_code=429)
    try:
        # Antes de leer el formulario: si no, un envío de varios GB se volcaría entero a un temporal antes de rechazarlo.
        if int(request.headers.get("content-length") or 0) > documentos.MAX_ARCHIVO + 64 * 1024:
            raise documentos.DocumentoError("El archivo no puede superar 15 MB.")
        formulario = await request.form()
        archivo = formulario.get("archivo")
        if not archivo or not hasattr(archivo, "read"):
            raise documentos.DocumentoError("Falta el campo archivo.")
        contenido = await archivo.read(documentos.MAX_ARCHIVO + 1)
        doc = await asyncio.to_thread(documentos.crear, _uid(request), archivo.filename, contenido)
        documentos.programar_documento(_uid(request), doc)
        return {"documento": doc}
    except documentos.DocumentoError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.get("/api/documentos/{doc_id:int}/archivo")
async def archivo(doc_id: int, request: Request):
    item = await asyncio.to_thread(documentos.ruta_archivo, _uid(request), doc_id)
    if not item or not item[1].is_file():
        return JSONResponse({"error": "Documento no encontrado."}, status_code=404)
    return Response(item[1].read_bytes(), media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{item[0]["nombre"]}"',
                             "X-Content-Type-Options": "nosniff"})


@router.delete("/api/documentos/{doc_id:int}")
async def borrar(doc_id: int, request: Request):
    if not await asyncio.to_thread(documentos.borrar, _uid(request), doc_id):
        return JSONResponse({"error": "Documento no encontrado."}, status_code=404)
    return {"ok": True}


@router.post("/api/documentos/buscar")
async def buscar(request: Request):
    try:
        d = await request.json()
        resultados = await documentos.buscar(_uid(request), d.get("pregunta", ""), doc_id=d.get("doc_id"))
        return {"resultados": resultados}
    except (ValueError, TypeError):
        return JSONResponse({"error": "Pregunta no válida."}, status_code=400)
