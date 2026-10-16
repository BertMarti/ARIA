"""Ubicación temporal del dispositivo para consultas sensibles al lugar."""
import math
import time
from contextlib import closing

from . import config, db, mapas

CADUCIDAD = 12 * 3600
_provincia_casa = None

# ISO 3166-2 de las 50 provincias y las dos ciudades autónomas -> código INE.
PROVINCIAS = {
    "A": "03", "AB": "02", "AL": "04", "AV": "05", "B": "08", "BA": "06", "BI": "48", "BU": "09",
    "C": "15", "CA": "11", "CC": "10", "CO": "14", "CR": "13", "CS": "12", "CU": "16", "GC": "35",
    "GI": "17", "GR": "18", "GU": "19", "H": "21", "HU": "22", "J": "23", "L": "25", "LE": "24",
    "LO": "26", "LU": "27", "M": "28", "MA": "29", "ML": "52", "MU": "30", "NA": "31", "O": "33",
    "OR": "32", "P": "34", "PM": "07", "PO": "36", "S": "39", "SA": "37", "SE": "41", "SG": "40",
    "SO": "42", "SS": "20", "T": "43", "TE": "44", "TF": "38", "TO": "45", "V": "46", "VA": "47",
    "VI": "01", "ZA": "49", "Z": "50", "CE": "51",
}


class UbicacionError(ValueError):
    pass


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.execute("""CREATE TABLE IF NOT EXISTS ubicaciones (
            user_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
            lat REAL NOT NULL, lon REAL NOT NULL, nombre TEXT, provincia TEXT, ts REAL NOT NULL)""")


# Comunidades uniprovinciales: si Nominatim no trae el nivel de provincia, vale el de comunidad.
UNIPROVINCIALES = {"MD": "28", "AS": "33", "CB": "39", "RI": "26", "NC": "31", "MC": "30", "IB": "07", "CE": "51", "ML": "52"}


def _provincia(codigo: str | None, comunidad: str | None = None) -> str | None:
    if codigo:
        return PROVINCIAS.get(str(codigo).upper().removeprefix("ES-"))
    if comunidad:
        return UNIPROVINCIALES.get(str(comunidad).upper().removeprefix("ES-"))
    return None


def publico(d: dict | None) -> dict:
    """Lo que ve el navegador: nunca las coordenadas (y de casa, ni el nombre del pueblo)."""
    if d and d.get("origen") == "dispositivo":
        return {"origen": "dispositivo", "nombre": d.get("nombre") or "Ubicación actual"}
    return {"origen": "casa", "nombre": "Casa"}


def _casa() -> dict | None:
    global _provincia_casa
    if config.LAT is None or config.LON is None:
        return None
    if _provincia_casa is None:
        _provincia_casa = config.PROVINCIA
    return {"lat": config.LAT, "lon": config.LON, "nombre": config.CIUDAD.split(",")[0].strip() or "Casa",
            "provincia": _provincia_casa, "origen": "casa"}


def actual(uid: int) -> dict | None:
    iniciar()   # idempotente: también vale si el arranque aún no la ha creado
    with closing(db._con()) as con:
        fila = con.execute("SELECT lat, lon, nombre, provincia, ts FROM ubicaciones WHERE user_id=?", (uid,)).fetchone()
    if fila and time.time() - fila["ts"] < CADUCIDAD:
        return {"lat": fila["lat"], "lon": fila["lon"], "nombre": fila["nombre"], "provincia": fila["provincia"],
                "origen": "dispositivo"}
    return _casa()


async def fijar(uid: int, lat, lon) -> dict:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise UbicacionError("Las coordenadas no son válidas.")
    if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise UbicacionError("Las coordenadas están fuera de rango.")
    lat, lon = round(lat, 2), round(lon, 2)
    with closing(db._con()) as con:
        anterior = con.execute("SELECT lat, lon, nombre, provincia FROM ubicaciones WHERE user_id=?", (uid,)).fetchone()
    if anterior and mapas._distancia(lat, lon, anterior["lat"], anterior["lon"]) < 3000:
        nombre, provincia = anterior["nombre"], anterior["provincia"]
    else:
        info = await mapas.inversa(lat, lon)
        nombre, provincia = info.get("nombre"), _provincia(info.get("provincia"), info.get("comunidad"))
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO ubicaciones(user_id,lat,lon,nombre,provincia,ts) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET lat=excluded.lat,lon=excluded.lon,nombre=excluded.nombre,"
                    "provincia=excluded.provincia,ts=excluded.ts", (uid, lat, lon, nombre, provincia, time.time()))
    return actual(uid)


async def provincia_casa() -> str | None:
    global _provincia_casa
    casa = _casa()
    if not casa:
        return None
    if _provincia_casa:
        return _provincia_casa
    try:
        info = await mapas.inversa(casa["lat"], casa["lon"])
        _provincia_casa = _provincia(info.get("provincia"), info.get("comunidad"))
    except mapas.MapasError:
        pass
    return _provincia_casa


def olvidar(uid: int) -> None:
    with closing(db._con()) as con, con:
        con.execute("DELETE FROM ubicaciones WHERE user_id=?", (uid,))
