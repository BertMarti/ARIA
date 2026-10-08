def registrar(aria):
    @aria.herramienta("roto_herramienta", "No debería quedar registrada.", intenciones=[r"\broto\b"])
    async def roto_herramienta() -> str:
        return "x"

    aria.router().get("/roto")(lambda: 1)
    raise RuntimeError("explota a propósito")
