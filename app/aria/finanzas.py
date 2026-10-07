"""Finanzas personales por usuario (tablas fin_* de data/aria.db).

TODA función recibe `uid` y filtra por `user_id`: cada usuario solo ve y cambia sus datos.
Los importes se guardan en céntimos (enteros): gasto < 0, ingreso > 0.
Sin bancos ni APIs financieras: los datos llegan a mano, por el chat o importando un CSV.
"""
import re
import time
import unicodedata
from collections import Counter
from contextlib import closing
from datetime import date

from . import db

CATEGORIAS_DEFECTO = ("Supermercado", "Restaurantes", "Transporte", "Vivienda", "Suministros",
                      "Telefonía e internet", "Suscripciones", "Compras", "Salud", "Ocio", "Seguros",
                      "Educación", "Efectivo", "Comisiones", "Transferencias", "Ingresos", "Otros")

# Reglas integradas (patrón sobre el concepto normalizado -> categoría). Las del usuario mandan.
REGLAS_DEFECTO = (
    (r"mercadona|carrefour|lidl|\bdia\b|alcampo|eroski|consum|aldi|hipercor|supermercad|ahorramas|bonpreu|condis|spar\b", "Supermercado"),
    (r"restaurante|\bbar\b|cafeteria|glovo|just ?eat|uber ?eats|deliveroo|telepizza|burger|mcdonald|kfc|domino|foodhall", "Restaurantes"),
    (r"repsol|cepsa|\bbp\b|galp|shell|gasolin|carburante|renfe|metro|\bemt\b|cabify|uber|bolt|blablacar|parking|aparcamiento|peaje|autopista|iryo|ouigo|taxi", "Transporte"),
    (r"alquiler|hipoteca|comunidad de propietarios|\bibi\b", "Vivienda"),
    (r"iberdrola|endesa|naturgy|repsol luz|holaluz|totalenergies|canal de isabel|aguas de|emasesa|aqualia|gas natural", "Suministros"),
    (r"movistar|vodafone|orange|yoigo|digi|pepephone|masmovil|lowi|simyo|jazztel|o2\b|finetwork", "Telefonía e internet"),
    (r"netflix|spotify|hbo|\bmax\b|disney|prime video|amazon prime|apple\.com|icloud|google one|youtube|dazn|filmin|movistar plus|patreon|chatgpt|openai", "Suscripciones"),
    (r"amazon|aliexpress|zara|primark|el corte ingles|decathlon|ikea|leroy|mediamarkt|pccomponentes|fnac|shein|temu", "Compras"),
    (r"farmacia|clinica|dentista|hospital|optica|sanitas|adeslas|asisa|fisio", "Salud"),
    (r"cine|teatro|concierto|ticketmaster|entradas|steam|playstation|nintendo|xbox|gimnasio|basic ?fit|museo", "Ocio"),
    (r"seguro|mapfre|mutua|allianz|axa|linea directa|generali|reale|zurich", "Seguros"),
    (r"colegio|universidad|academia|matricula|libreria|udemy|coursera", "Educación"),
    (r"cajero|reintegro|retirada de efectivo|atm", "Efectivo"),
    (r"comision|intereses deudores|mantenimiento de cuenta|cuota tarjeta", "Comisiones"),
    (r"nomina|salario|pension|prestacion|devolucion hacienda|abono de intereses", "Ingresos"),
    (r"bizum|transferencia|traspaso", "Transferencias"),
)
MAX_CONCEPTO = 200
MAX_CATEGORIA = 40
MAX_IMPORTE = 100_000_000 * 100  # cien millones de euros, en céntimos


class FinanzasError(Exception):
    """Error de validación (mensaje en español)."""


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS fin_movimientos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                concepto TEXT NOT NULL,
                concepto_norm TEXT NOT NULL,
                importe INTEGER NOT NULL,
                categoria TEXT,
                cuenta TEXT,
                origen TEXT NOT NULL CHECK (origen IN ('manual','csv')),
                creado REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_fin_mov ON fin_movimientos(user_id, fecha);
            CREATE INDEX IF NOT EXISTS idx_fin_dedup ON fin_movimientos(user_id, fecha, importe, concepto_norm);
            CREATE TABLE IF NOT EXISTS fin_categorias (
                user_id INTEGER NOT NULL, nombre TEXT NOT NULL, PRIMARY KEY (user_id, nombre));
            CREATE TABLE IF NOT EXISTS fin_presupuestos (
                user_id INTEGER NOT NULL, categoria TEXT NOT NULL, importe INTEGER NOT NULL,
                PRIMARY KEY (user_id, categoria));
            CREATE TABLE IF NOT EXISTS fin_reglas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                patron TEXT NOT NULL, categoria TEXT NOT NULL, UNIQUE (user_id, patron));
        """)


# --- Utilidades -----------------------------------------------------------------------------------
def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.& ]", " ", t)).strip()


def euros(cent: int) -> str:
    s = f"{abs(cent) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if cent < 0 else "") + s + " €"


def a_centimos(v) -> int:
    """Número o texto ('12,50', '-3.20', 12.5) -> céntimos."""
    if isinstance(v, bool):
        raise FinanzasError("Importe no válido.")
    if isinstance(v, int):
        c = v * 100
    elif isinstance(v, float):
        c = round(v * 100)
    else:
        from .finanzas_csv import parse_importe
        s = str(v or "").strip()
        c = parse_importe(s, "." if re.fullmatch(r"-?\d+\.\d{1,2}", s) else ",")
        if c is None:
            raise FinanzasError("Importe no válido.")
    if c == 0 or abs(c) > MAX_IMPORTE:
        raise FinanzasError("Importe no válido.")
    return c


def mes_valido(mes: str | None) -> str:
    """'2026-10' / '10/2026' / None (mes actual) -> 'AAAA-MM'."""
    if not mes or str(mes).strip().lower() in ("este mes", "actual", "hoy"):
        return date.today().strftime("%Y-%m")
    s = str(mes).strip()
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})", s):
        y, mm = int(m.group(1)), int(m.group(2))
    elif m := re.fullmatch(r"(\d{1,2})[/-](\d{4})", s):
        y, mm = int(m.group(2)), int(m.group(1))
    else:
        raise FinanzasError("Mes no válido: usa AAAA-MM (por ejemplo 2026-10).")
    if not (1 <= mm <= 12 and 2000 <= y <= 2100):
        raise FinanzasError("Mes no válido: usa AAAA-MM (por ejemplo 2026-10).")
    return f"{y:04d}-{mm:02d}"


def fecha_valida(f: str | None) -> str:
    from .finanzas_csv import parse_fecha
    if not f or str(f).strip().lower() == "hoy":
        return date.today().isoformat()
    r = parse_fecha(str(f))
    if not r:
        raise FinanzasError("Fecha no válida: usa dd/mm/aaaa o aaaa-mm-dd.")
    return r


def _texto(t, maximo: int, campo: str) -> str:
    t = " ".join(str(t or "").split())[:maximo]
    if not t:
        raise FinanzasError(f"Falta el {campo}.")
    return t


# --- Categorías y reglas ----------------------------------------------------------------------------
def categorias(uid: int) -> list:
    with closing(db._con()) as con, con:
        filas = [r[0] for r in con.execute("SELECT nombre FROM fin_categorias WHERE user_id=? ORDER BY nombre", (uid,))]
        if not filas:
            con.executemany("INSERT OR IGNORE INTO fin_categorias (user_id, nombre) VALUES (?,?)",
                            [(uid, c) for c in CATEGORIAS_DEFECTO])
            filas = sorted(CATEGORIAS_DEFECTO)
    return filas


def _categoria_valida(uid: int, nombre) -> str | None:
    if nombre is None or str(nombre).strip() == "":
        return None
    n = _texto(nombre, MAX_CATEGORIA, "nombre de la categoría")
    existentes = {c.lower(): c for c in categorias(uid)}
    if n.lower() in existentes:
        return existentes[n.lower()]
    with closing(db._con()) as con, con:
        if con.execute("SELECT COUNT(*) FROM fin_categorias WHERE user_id=?", (uid,)).fetchone()[0] >= 60:
            raise FinanzasError("Demasiadas categorías (máximo 60).")
        con.execute("INSERT OR IGNORE INTO fin_categorias (user_id, nombre) VALUES (?,?)", (uid, n))
    return n


def reglas(uid: int) -> list:
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute("SELECT id, patron, categoria FROM fin_reglas WHERE user_id=? ORDER BY patron", (uid,))]


def anadir_regla(uid: int, patron: str, categoria: str) -> dict:
    p = normalizar(patron)[:60]
    if len(p) < 3:
        raise FinanzasError("El texto de la regla debe tener al menos 3 caracteres.")
    cat = _categoria_valida(uid, categoria)
    if not cat:
        raise FinanzasError("Falta la categoría.")
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO fin_reglas (user_id, patron, categoria) VALUES (?,?,?) "
                    "ON CONFLICT(user_id, patron) DO UPDATE SET categoria=excluded.categoria", (uid, p, cat))
        # recategoriza lo que coincide y aún no tenía categoría o tenía «Otros»
        n = con.execute("UPDATE fin_movimientos SET categoria=? WHERE user_id=? AND instr(concepto_norm, ?) > 0 "
                        "AND (categoria IS NULL OR categoria='Otros')", (cat, uid, p)).rowcount
    return {"patron": p, "categoria": cat, "actualizados": n}


def borrar_regla(uid: int, rid: int) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM fin_reglas WHERE id=? AND user_id=?", (rid, uid)).rowcount > 0


def categorizar(uid: int, concepto: str, importe: int, _reglas: list | None = None) -> str | None:
    n = normalizar(concepto)
    for r in (_reglas if _reglas is not None else reglas(uid)):
        if r["patron"] in n:
            return r["categoria"]
    for patron, cat in REGLAS_DEFECTO:
        if re.search(patron, n):
            return cat
    return "Ingresos" if importe > 0 else None


# --- Movimientos ------------------------------------------------------------------------------------
def _fila(r) -> dict:
    return {"id": r["id"], "fecha": r["fecha"], "concepto": r["concepto"], "importe": r["importe"],
            "categoria": r["categoria"], "cuenta": r["cuenta"], "origen": r["origen"]}


def registrar(uid: int, fecha, concepto, importe, categoria=None, cuenta=None, origen: str = "manual") -> dict:
    f = fecha_valida(fecha)
    c = _texto(concepto, MAX_CONCEPTO, "concepto")
    imp = a_centimos(importe)
    cat = _categoria_valida(uid, categoria) or categorizar(uid, c, imp)
    cta = " ".join(str(cuenta or "").split())[:60] or None
    with closing(db._con()) as con, con:
        cur = con.execute("INSERT INTO fin_movimientos (user_id, fecha, concepto, concepto_norm, importe, categoria, "
                          "cuenta, origen, creado) VALUES (?,?,?,?,?,?,?,?,?)",
                          (uid, f, c, normalizar(c), imp, cat, cta, origen, time.time()))
        r = con.execute("SELECT * FROM fin_movimientos WHERE id=?", (cur.lastrowid,)).fetchone()
    return _fila(r)


def obtener(uid: int, mid: int) -> dict | None:
    with closing(db._con()) as con:
        r = con.execute("SELECT * FROM fin_movimientos WHERE id=? AND user_id=?", (mid, uid)).fetchone()
    return _fila(r) if r else None


def actualizar(uid: int, mid: int, cambios: dict) -> dict:
    actual = obtener(uid, mid)
    if not actual:
        raise FinanzasError("Movimiento no encontrado.")
    campos = {}
    if "fecha" in cambios:
        campos["fecha"] = fecha_valida(cambios["fecha"])
    if "concepto" in cambios:
        campos["concepto"] = _texto(cambios["concepto"], MAX_CONCEPTO, "concepto")
        campos["concepto_norm"] = normalizar(campos["concepto"])
    if "importe" in cambios:
        campos["importe"] = a_centimos(cambios["importe"])
    if "categoria" in cambios:
        campos["categoria"] = _categoria_valida(uid, cambios["categoria"])
    if "cuenta" in cambios:
        campos["cuenta"] = " ".join(str(cambios["cuenta"] or "").split())[:60] or None
    if campos:
        sets = ", ".join(f"{k}=?" for k in campos)  # claves de una lista fija
        with closing(db._con()) as con, con:
            con.execute(f"UPDATE fin_movimientos SET {sets} WHERE id=? AND user_id=?",  # noqa: S608
                        (*campos.values(), mid, uid))
    if cambios.get("aplicar_a_similares") and campos.get("categoria"):
        clave = _clave_similar(actual["concepto"])
        if clave:
            anadir_regla(uid, clave, campos["categoria"])
    return obtener(uid, mid)


def _clave_similar(concepto: str) -> str:
    """Parte estable de un concepto para crear una regla («COMPRA TARJ. 1234 MERCADONA VALENCIA» -> «mercadona valencia»)."""
    palabras = [p for p in normalizar(concepto).split() if not re.search(r"\d", p)
                and p not in ("compra", "tarj", "tarj.", "tarjeta", "pago", "en", "de", "con", "recibo", "transferencia", "a", "favor")]
    return " ".join(palabras[:3])


def borrar(uid: int, mid: int) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM fin_movimientos WHERE id=? AND user_id=?", (mid, uid)).rowcount > 0


def listar(uid: int, mes: str | None = None, categoria: str | None = None, texto: str | None = None,
           limite: int = 500) -> list:
    sql, args = "SELECT * FROM fin_movimientos WHERE user_id=?", [uid]
    if mes:
        sql += " AND substr(fecha,1,7)=?"
        args.append(mes_valido(mes))
    if categoria:
        if categoria == "__sin__":
            sql += " AND categoria IS NULL"
        else:
            sql += " AND categoria=?"
            args.append(str(categoria))
    if texto:
        sql += " AND instr(concepto_norm, ?) > 0"
        args.append(normalizar(texto))
    sql += " ORDER BY fecha DESC, id DESC LIMIT ?"
    args.append(max(1, min(int(limite), 2000)))
    with closing(db._con()) as con:
        return [_fila(r) for r in con.execute(sql, args)]


def meses(uid: int) -> list:
    with closing(db._con()) as con:
        return [r[0] for r in con.execute("SELECT DISTINCT substr(fecha,1,7) m FROM fin_movimientos WHERE user_id=? "
                                          "ORDER BY m DESC LIMIT 60", (uid,))]


# --- Importación ------------------------------------------------------------------------------------
def importar(uid: int, movimientos: list, cuenta: str | None = None) -> dict:
    """Inserta movimientos del CSV evitando duplicados por (fecha, importe, concepto).

    Si el CSV trae k filas idénticas y ya hay j guardadas, se insertan k - j (así reimportar el
    mismo extracto no duplica, pero dos cafés iguales el mismo día no se pierden)."""
    cta = " ".join(str(cuenta or "").split())[:60] or None
    claves = Counter((m["fecha"], m["importe"], normalizar(m["concepto"])) for m in movimientos)
    rg = reglas(uid)
    insertados = duplicados = 0
    with closing(db._con()) as con, con:
        existentes = Counter()
        for (f, imp, cn) in claves:
            existentes[(f, imp, cn)] = con.execute(
                "SELECT COUNT(*) FROM fin_movimientos WHERE user_id=? AND fecha=? AND importe=? AND concepto_norm=?",
                (uid, f, imp, cn)).fetchone()[0]
        vistos = Counter()
        ahora = time.time()
        for m in movimientos:
            k = (m["fecha"], m["importe"], normalizar(m["concepto"]))
            vistos[k] += 1
            if vistos[k] <= existentes[k]:
                duplicados += 1
                continue
            cat = categorizar(uid, m["concepto"], m["importe"], rg)
            con.execute("INSERT INTO fin_movimientos (user_id, fecha, concepto, concepto_norm, importe, categoria, "
                        "cuenta, origen, creado) VALUES (?,?,?,?,?,?,?,'csv',?)",
                        (uid, m["fecha"], m["concepto"][:MAX_CONCEPTO], k[2], m["importe"], cat,
                         m.get("cuenta") or cta, ahora))
            insertados += 1
    categorias(uid)
    return {"insertados": insertados, "duplicados": duplicados}


# --- Resúmenes ---------------------------------------------------------------------------------------
def resumen_mes(uid: int, mes: str | None = None) -> dict:
    m = mes_valido(mes)
    with closing(db._con()) as con:
        r = con.execute("SELECT COALESCE(SUM(CASE WHEN importe>0 THEN importe END),0) ing, "
                        "COALESCE(SUM(CASE WHEN importe<0 THEN importe END),0) gas, COUNT(*) n "
                        "FROM fin_movimientos WHERE user_id=? AND substr(fecha,1,7)=?", (uid, m)).fetchone()
    return {"mes": m, "ingresos": r["ing"], "gastos": -r["gas"], "balance": r["ing"] + r["gas"], "movimientos": r["n"],
            "categorias": gastos_por_categoria(uid, m)}


def gastos_por_categoria(uid: int, mes: str | None = None) -> list:
    m = mes_valido(mes)
    with closing(db._con()) as con:
        filas = con.execute("SELECT COALESCE(categoria,'Sin categoría') c, -SUM(importe) t, COUNT(*) n "
                            "FROM fin_movimientos WHERE user_id=? AND substr(fecha,1,7)=? AND importe<0 "
                            "GROUP BY c ORDER BY t DESC", (uid, m)).fetchall()
    return [{"categoria": f["c"], "total": f["t"], "movimientos": f["n"]} for f in filas]


def comparar_meses(uid: int, mes_a: str | None, mes_b: str | None) -> dict:
    a, b = resumen_mes(uid, mes_a), resumen_mes(uid, mes_b)
    cats = {c["categoria"]: [c["total"], 0] for c in a["categorias"]}
    for c in b["categorias"]:
        cats.setdefault(c["categoria"], [0, 0])[1] = c["total"]
    return {"a": {k: a[k] for k in ("mes", "ingresos", "gastos", "balance")},
            "b": {k: b[k] for k in ("mes", "ingresos", "gastos", "balance")},
            "categorias": sorted(({"categoria": k, "a": v[0], "b": v[1], "diferencia": v[1] - v[0]}
                                  for k, v in cats.items()), key=lambda x: -abs(x["diferencia"]))}


def fijar_presupuesto(uid: int, categoria, importe) -> dict:
    cat = _categoria_valida(uid, categoria)
    if not cat:
        raise FinanzasError("Falta la categoría.")
    cent = abs(a_centimos(importe)) if str(importe).strip() not in ("0", "0,00", "0.00", "") else 0
    with closing(db._con()) as con, con:
        if cent == 0:
            con.execute("DELETE FROM fin_presupuestos WHERE user_id=? AND categoria=?", (uid, cat))
        else:
            con.execute("INSERT INTO fin_presupuestos (user_id, categoria, importe) VALUES (?,?,?) "
                        "ON CONFLICT(user_id, categoria) DO UPDATE SET importe=excluded.importe", (uid, cat, cent))
    return {"categoria": cat, "importe": cent}


def estado_presupuestos(uid: int, mes: str | None = None) -> list:
    m = mes_valido(mes)
    gastado = {c["categoria"]: c["total"] for c in gastos_por_categoria(uid, m)}
    with closing(db._con()) as con:
        pres = con.execute("SELECT categoria, importe FROM fin_presupuestos WHERE user_id=? ORDER BY categoria",
                           (uid,)).fetchall()
    out = []
    for p in pres:
        g = gastado.get(p["categoria"], 0)
        out.append({"categoria": p["categoria"], "presupuesto": p["importe"], "gastado": g,
                    "restante": p["importe"] - g, "porcentaje": round(g * 100 / p["importe"], 1) if p["importe"] else 0,
                    "superado": g > p["importe"]})
    return out


def sin_categoria(uid: int, limite: int = 30) -> list:
    """Conceptos distintos sin categoría (para la sugerencia opcional de la nube)."""
    with closing(db._con()) as con:
        return [r[0] for r in con.execute(
            "SELECT concepto FROM fin_movimientos WHERE user_id=? AND categoria IS NULL "
            "GROUP BY concepto_norm ORDER BY MAX(fecha) DESC LIMIT ?", (uid, limite))]
