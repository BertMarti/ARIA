"""Lectura de extractos CSV de bancos españoles (sin dependencias).

Admite: separador `;`, `,` o tabulador; coma decimal o punto decimal; fechas dd/mm/aaaa,
dd-mm-aaaa, dd/mm/aa o aaaa-mm-dd; una columna «Importe» o dos columnas Debe/Haber (Cargo/Abono);
UTF-8 (con o sin BOM), latin-1/cp1252; líneas de cabecera previas (titular, número de cuenta...).
"""
import csv
import io
import re
import unicodedata
from datetime import date

MAX_BYTES = 2 * 1024 * 1024
MAX_FILAS = 5000

CAMPOS = ("fecha", "concepto", "importe", "debe", "haber", "cuenta")
# Palabras que identifican cada columna en la cabecera (sin tildes, en minúsculas). El orden importa:
# «fecha operacion» gana a «fecha valor».
_CLAVES = {
    "fecha": ("fecha operacion", "f. operacion", "fecha de operacion", "fecha", "f.operacion", "f. valor",
              "fecha valor", "date"),
    "concepto": ("concepto", "descripcion", "movimiento", "detalle", "observaciones", "comercio", "description"),
    "importe": ("importe", "cantidad", "amount", "importe (eur)", "importe eur"),
    "debe": ("debe", "cargo", "cargos", "gastos", "salidas"),
    "haber": ("haber", "abono", "abonos", "ingresos", "entradas"),
    "cuenta": ("cuenta", "iban", "tarjeta"),
}


class CsvError(Exception):
    """Error legible al importar."""


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def decodificar(datos: bytes) -> tuple:
    if len(datos) > MAX_BYTES:
        raise CsvError("El archivo es demasiado grande (máximo 2 MB).")
    if b"\x00" in datos[:4096]:
        raise CsvError("No parece un archivo CSV de texto.")
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return datos.decode(cod), ("utf-8" if cod == "utf-8-sig" else cod)
        except UnicodeDecodeError:
            continue
    raise CsvError("No se pudo leer el archivo.")  # pragma: no cover - latin-1 siempre decodifica


def detectar_separador(texto: str) -> str:
    lineas = [l for l in texto.splitlines() if l.strip()][:30]
    mejor, puntos = ";", -1
    for sep in (";", "\t", ","):
        cuentas = [len(next(csv.reader([l], delimiter=sep))) for l in lineas]
        # el separador correcto da muchas columnas y el mismo número en casi todas las líneas
        if not cuentas:
            continue
        moda = max(set(cuentas), key=cuentas.count)
        p = (cuentas.count(moda) * 10 + moda) if moda > 1 else 0
        if p > puntos:
            mejor, puntos = sep, p
    return mejor


def _columna(celda: str):
    n = _norm(celda)
    for campo, claves in _CLAVES.items():
        for c in claves:
            if n == c or n.startswith(c + " ") or n.startswith(c + "(") or (len(c) > 4 and c in n):
                return campo
    return None


def localizar_cabecera(filas: list) -> int:
    """Índice de la fila de cabecera: la primera (de las 20 primeras) con fecha y concepto/importe."""
    for i, f in enumerate(filas[:20]):
        campos = {_columna(c) for c in f}
        if "fecha" in campos and ({"concepto", "importe", "debe", "haber"} & campos):
            return i
    raise CsvError("No encuentro la fila de cabecera (debe tener columnas de fecha y concepto o importe).")


def sugerir_mapeo(cabecera: list) -> dict:
    mapeo = {k: None for k in CAMPOS}
    for i, celda in enumerate(cabecera):
        campo = _columna(celda)
        if campo and mapeo[campo] is None:
            mapeo[campo] = i
    return mapeo


_FECHA_ES = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})$")
_FECHA_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")


def parse_fecha(t: str) -> str | None:
    t = (t or "").strip()
    try:
        if m := _FECHA_ES.match(t):
            d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            y += 2000 if y < 100 else 0
            return date(y, mth, d).isoformat()
        if m := _FECHA_ISO.match(t):
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None
    return None


def detectar_decimal(valores: list) -> str:
    coma = sum(1 for v in valores if re.search(r",\d{1,2}\s*(€|eur)?\s*-?$", (v or "").strip(), re.I))
    punto = sum(1 for v in valores if re.search(r"\.\d{1,2}\s*(€|eur)?\s*-?$", (v or "").strip(), re.I))
    return "." if punto > coma else ","


def parse_importe(t: str, decimal: str = ",") -> int | None:
    """Texto -> céntimos (int). '1.234,56' -> 123456; '-12,30 €' -> -1230; '(5,00)' -> -500."""
    s = (t or "").strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    s = re.sub(r"(?i)(€|eur)", "", s)
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    if s.endswith("-"):
        neg, s = True, s[:-1]
    if s.startswith(("-", "−")):
        neg, s = True, s[1:]
    elif s.startswith("+"):
        s = s[1:]
    if not re.fullmatch(r"[\d.,']+", s) or not re.search(r"\d", s):
        return None
    miles = "." if decimal == "," else ","
    if "," in s and "." in s:  # el último separador es el decimal
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        miles = "." if decimal == "," else ","
    s = s.replace("'", "").replace(miles, "")
    if s.count(decimal) > 1:
        return None
    ent, _, dec = s.partition(decimal)
    if len(dec) > 2:
        return None
    try:
        cent = int(ent or "0") * 100 + int((dec + "00")[:2])
    except ValueError:
        return None
    return -cent if neg else cent


def leer(datos: bytes) -> dict:
    """Primer paso: decodifica, detecta separador y cabecera y sugiere el mapeo de columnas."""
    texto, cod = decodificar(datos)
    sep = detectar_separador(texto)
    filas = [f for f in csv.reader(io.StringIO(texto), delimiter=sep) if any(c.strip() for c in f)]
    if not filas:
        raise CsvError("El archivo está vacío.")
    i = localizar_cabecera(filas)
    cab = [c.strip() for c in filas[i]]
    cuerpo = filas[i + 1:i + 1 + MAX_FILAS]
    return {"codificacion": cod, "separador": sep, "cabecera": cab, "mapeo": sugerir_mapeo(cab),
            "filas": cuerpo, "total": len(cuerpo)}


def validar_mapeo(mapeo: dict, ncols: int) -> dict:
    out = {}
    for k in CAMPOS:
        v = (mapeo or {}).get(k)
        if v is None or v == "":
            out[k] = None
            continue
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise CsvError("Mapeo de columnas no válido.") from None
        if not 0 <= v < ncols:
            raise CsvError("Mapeo de columnas no válido.")
        out[k] = v
    if out["fecha"] is None or out["concepto"] is None:
        raise CsvError("Indica las columnas de fecha y concepto.")
    if out["importe"] is None and out["debe"] is None and out["haber"] is None:
        raise CsvError("Indica la columna de importe (o las de debe/haber).")
    return out


def convertir(filas: list, mapeo: dict, ncols: int) -> dict:
    """Filas del CSV -> movimientos {fecha, concepto, importe(céntimos), cuenta}."""
    m = validar_mapeo(mapeo, ncols)
    col = lambda f, k: f[m[k]].strip() if m[k] is not None and m[k] < len(f) else ""  # noqa: E731
    muestras = [col(f, k) for f in filas[:200] for k in ("importe", "debe", "haber") if m[k] is not None]
    dec = detectar_decimal(muestras)
    out, errores = [], []
    for n, f in enumerate(filas, start=1):
        fecha = parse_fecha(col(f, "fecha"))
        concepto = " ".join(col(f, "concepto").split())[:200]
        if m["importe"] is not None:
            imp = parse_importe(col(f, "importe"), dec)
        else:
            debe = parse_importe(col(f, "debe"), dec) if m["debe"] is not None else None
            haber = parse_importe(col(f, "haber"), dec) if m["haber"] is not None else None
            imp = None if debe is None and haber is None else (abs(haber or 0) - abs(debe or 0))
        if not fecha or imp is None or not concepto:
            errores.append(n)
            continue
        out.append({"fecha": fecha, "concepto": concepto, "importe": imp, "cuenta": col(f, "cuenta")[:60] or None})
    return {"movimientos": out, "errores": errores, "decimal": dec}
