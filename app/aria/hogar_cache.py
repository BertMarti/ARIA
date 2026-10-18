"""Caché «obsoleto mientras se refresca» para la pantalla Hogar: se responde al momento con lo último conocido y, si
está algo viejo, se pide de nuevo en segundo plano. El router tarda ~6 s y las cámaras ~4 s: sin esto, la pantalla
esperaba a todos."""
import asyncio
import logging
import time

log = logging.getLogger("aria.hogar")
_datos: dict = {}     # clave -> (momento, valor)
_tareas: dict = {}    # clave -> tarea de refresco en curso


async def obtener(clave: str, funcion, fresco: float = 60, maximo: float = 900):
    """Valor de `funcion()` con caché. Más nuevo que `fresco`: tal cual. Hasta `maximo`: tal cual y se refresca
    detrás. Más viejo o sin dato: se espera a la respuesta (y si falla, la excepción llega al llamante)."""
    ahora = time.monotonic()
    guardado = _datos.get(clave)
    if guardado and ahora - guardado[0] < fresco:
        return guardado[1]
    if guardado and ahora - guardado[0] < maximo:
        tarea = _tareas.get(clave)
        if tarea is None or tarea.done():
            _tareas[clave] = asyncio.create_task(_refrescar(clave, funcion))
        return guardado[1]
    valor = await funcion()
    _datos[clave] = (time.monotonic(), valor)
    return valor


async def refrescar(clave: str, funcion) -> None:
    """Refresca ya (lo usa el precalentado en segundo plano)."""
    await _refrescar(clave, funcion)


async def _refrescar(clave, funcion):
    try:
        _datos[clave] = (time.monotonic(), await funcion())
    except Exception:  # noqa: BLE001 - se seguirá mostrando lo último conocido
        log.info("No se pudo refrescar %s", clave)


def invalidar(*claves: str) -> None:
    """Tras un cambio hecho desde ARIA: la siguiente lectura va a buscar el dato real."""
    for c in claves:
        _datos.pop(c, None)


def limpiar() -> None:
    _datos.clear()
    _tareas.clear()
