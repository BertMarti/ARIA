"""Fechas locales (zona horaria ARIA_TZ): hoy, ayer y límites de un día.

Los límites usan el calendario local, no «24 horas»: el día del cambio de hora dura 23 o 25 h."""
from datetime import date, datetime, time as hora, timedelta
from zoneinfo import ZoneInfo

from . import config

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def zona() -> ZoneInfo:
    return ZoneInfo(config.TZ)


def ahora() -> datetime:
    return datetime.now(zona())


def hoy(ref: datetime | None = None) -> date:
    return (ref.astimezone(zona()) if ref else ahora()).date()


def ayer(ref: datetime | None = None) -> date:
    return hoy(ref) - timedelta(days=1)


def limites(dia: date) -> tuple[float, float]:
    """(inicio, fin) del día local como marcas de tiempo; el fin es exclusivo."""
    z = zona()
    return (datetime.combine(dia, hora.min, tzinfo=z).timestamp(),
            datetime.combine(dia + timedelta(days=1), hora.min, tzinfo=z).timestamp())


def texto_fecha(dia: date) -> str:
    return f"{DIAS[dia.weekday()]}, {dia.day} de {MESES[dia.month - 1]}"


def saludo_horario(ref: datetime | None = None) -> str:
    h = (ref.astimezone(zona()) if ref else ahora()).hour
    return "Buenos días" if 6 <= h < 13 else "Buenas tardes" if 13 <= h < 21 else "Buenas noches"
