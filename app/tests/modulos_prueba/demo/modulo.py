"""Módulo de prueba: dos herramientas, un chequeo y rutas para usuario y solo admin."""
from . import ayuda


def registrar(aria):
    @aria.herramienta("demo_eco", "Repite un texto (prueba de módulos).", {"texto": ("string", "Texto")}, ("texto",),
                      solo_lectura=True, roles=("admin", "usuario"), intenciones=[r"\bdemo-eco\b"])
    async def demo_eco(texto: str) -> str:
        return ayuda.prefijo(aria.config("DEMO_SALUDO", "eco")) + texto

    @aria.herramienta("demo_admin", "Acción de administrador (prueba de módulos).", agentes=("redes",),
                      intenciones=[(r"\bdemo-admin\b", r"!\bno\b")])
    async def demo_admin() -> str:
        raise aria.Error("fallo legible del módulo")

    @aria.chequeo("siempre-mal", intervalo_min=1, confirmaciones=1)
    async def siempre_mal():
        return ["algo va mal", aria.Problema("otra", "otra cosa", "grave")]

    r = aria.router(usuario=[("GET", "/hola"), ("GET", "/item/{n}")])

    @r.get("/hola")
    async def hola():
        return {"hola": True}

    @r.get("/item/{n}")
    async def item(n: int):
        return {"n": n}

    @r.get("/privado")
    async def privado():
        return {"privado": True}

    @r.post("/secreto")
    async def secreto():
        return {"secreto": True}
