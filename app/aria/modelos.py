"""Gestión de modelos de Ollama: listar, activar, descargar y borrar."""
import json

import httpx

from . import config

# Lista curada para una Raspberry Pi de 8 GB (nombre, descripción, tamaño aproximado).
CURADOS = [
    {"nombre": "llama3.2:3b", "descripcion": "Equilibrado y admite herramientas (recomendado)", "tamano": "2,0 GB"},
    {"nombre": "llama3.2:1b", "descripcion": "Muy rápido y ligero, más flojo con herramientas", "tamano": "1,3 GB"},
    {"nombre": "qwen2.5:3b", "descripcion": "Buen español y herramientas", "tamano": "1,9 GB"},
    {"nombre": "gemma2:2b", "descripcion": "Compacto; no admite herramientas", "tamano": "1,6 GB"},
]
NOMBRES_CURADOS = {m["nombre"] for m in CURADOS}


async def instalados() -> list | None:
    """Lista de {nombre, tamano} o None si Ollama no responde."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{config.OLLAMA_URL}/api/tags")
        return [{"nombre": m["name"], "tamano": m.get("size", 0)} for m in r.json().get("models", [])]
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def esta_instalado(nombre: str, lista: list) -> bool:
    nombres = {m["nombre"] for m in lista}
    return nombre in nombres or (":" not in nombre and f"{nombre}:latest" in nombres)


async def borrar(nombre: str) -> bool:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request("DELETE", f"{config.OLLAMA_URL}/api/delete", json={"model": nombre})
    return r.status_code == 200


async def descargar(nombre: str):
    """Generador de eventos de progreso de la descarga."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10)) as c:
            async with c.stream("POST", f"{config.OLLAMA_URL}/api/pull",
                                json={"model": nombre, "stream": True}) as r:
                async for linea in r.aiter_lines():
                    if linea.strip():
                        j = json.loads(linea)
                        if j.get("error"):
                            yield {"type": "error", "text": "Error al descargar el modelo."}
                            return
                        yield {"type": "progreso", "estado": j.get("status", ""),
                               "total": j.get("total"), "completado": j.get("completed")}
        yield {"type": "fin"}
    except httpx.HTTPError:
        yield {"type": "error", "text": "No se pudo contactar con Ollama."}
