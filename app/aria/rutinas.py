"""Rutinas: tareas de IA programadas por cada usuario («cada mañana a las 8, dime el tiempo y 3 titulares»).

Una rutina tiene nombre, horario, prompt, agente y canal. A su hora, el planificador de avisos (`avisos.tick`)
pasa el prompt por el mismo bucle del chat (`chat.responder`) como ese usuario, con su rol, sus agentes y su
memoria, pero:

- solo con cerebros en la nube (si solo queda el local, se salta y se deja una nota en la campana);
- solo con herramientas de consulta (`tools.RUTINAS`, cruzadas además con las del rol y del agente): una
  rutina nunca pausa el bloqueador, toca la VPN, apunta gastos, escanea ni crea o borra nada;
- con un tiempo máximo (`TIMEOUT_S`) y como mucho `MAX_SIMULTANEAS` a la vez.

El resultado se entrega por los canales de avisos (Telegram, push o los dos) y siempre queda en la campana.
Contra los disparos dobles (reinicios, dos ticks seguidos) cada ejecución programada se anota en
`avisos_estado` con la clave `rutina:<id>:<instante>` ANTES de ejecutarse (el patrón de `_ya_enviado`), y la
próxima hora se calcula y se guarda también antes. Si ARIA estuvo apagada más de `VENTANA_S`, la ejecución
atrasada se salta (no tiene sentido el tiempo de «hoy» a las once de la noche).
"""
import asyncio
import json
import logging
import re
import time
from contextlib import closing
from datetime import datetime, timedelta

from . import agentes, avisos, db, recordatorios, tiempo

log = logging.getLogger("aria.rutinas")

MAX_POR_USUARIO = 10
MIN_HORAS = 1          # intervalo mínimo entre dos ejecuciones
MAX_HORAS = 168
MAX_NOMBRE = 60
MAX_PROMPT = 1000
MAX_RESULTADO = 1700   # lo que va a la campana / Telegram (el resto, en la conversación)
TIMEOUT_S = 90
VENTANA_S = 3 * 3600
MAX_SIMULTANEAS = 2
CANALES = ("telegram", "push", "ambos", "web")
NOMBRE_CANAL = {"telegram": "Telegram", "push": "notificación", "ambos": "Telegram y notificación", "web": "solo la campana"}
_DIAS_PLURAL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"]

_en_curso: set = set()
_tareas: set = set()
_sem = asyncio.Semaphore(MAX_SIMULTANEAS)


class RutinaError(Exception):
    """Error legible (en español)."""


def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS rutinas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                nombre TEXT NOT NULL, prompt TEXT NOT NULL, agente TEXT NOT NULL DEFAULT 'aria',
                canal TEXT NOT NULL DEFAULT 'telegram', horario TEXT NOT NULL,
                activa INTEGER NOT NULL DEFAULT 1, proxima REAL, ultima REAL, ultimo_estado TEXT,
                ultimo_texto TEXT, conv_id TEXT, creado REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_rutinas_prox ON rutinas(activa, proxima);
            CREATE INDEX IF NOT EXISTS idx_rutinas_user ON rutinas(user_id);
        """)


# --- Horario -----------------------------------------------------------------------------------------------
_N_HORAS = {"una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
            "diez": 10, "once": 11, "doce": 12, "veinticuatro": 24}
_DIA_RE = r"(lunes|martes|miercoles|jueves|viernes|sabados?|domingos?)"


def interpretar_horario(texto: str) -> dict:
    """Español -> horario. «todos los días a las 8», «de lunes a viernes a las 7:30», «los lunes y jueves a las 9»,
    «los fines de semana a las 10», «cada 3 horas», «cada hora». Lanza RutinaError si no se entiende."""
    t = recordatorios._norm(texto)
    if not t:
        raise RutinaError("Dime cuándo debe ejecutarse (p. ej. «todos los días a las 8:00» o «cada 3 horas»).")
    if re.search(r"\bcada (\d+ |media |un cuarto de )?(minutos?|mins?|media hora|cuarto de hora)\b", t) \
            or re.search(r"\bcada media hora\b", t):
        raise RutinaError(f"Como mucho una vez por hora: el intervalo mínimo es {MIN_HORAS} h.")
    m = re.search(r"\bcada (?:(\d+|" + "|".join(_N_HORAS) + r") )?(horas?|h)\b", t)
    if m:
        n = int(m.group(1)) if (m.group(1) or "").isdigit() else _N_HORAS.get(m.group(1) or "una", 1)
        return normalizar_horario({"tipo": "cada", "horas": n})
    if re.search(r"\b(de lunes a viernes|entre semana|dias laborables|laborables)\b", t):
        dias = [0, 1, 2, 3, 4]
    elif re.search(r"\b(fines? de semana|sabados? y domingos?)\b", t):
        dias = [5, 6]
    else:
        nombres = re.findall(r"\b" + _DIA_RE + r"\b", t)
        orden = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
        dias = sorted({orden[n.rstrip("s") if n.startswith(("sabado", "domingo")) else n] for n in nombres})
    hm = recordatorios._hora_de(t)
    if hm is None:
        franja = next((f for f in ("madrugada", "mediodia", "tarde", "noche", "manana")
                       if re.search(rf"\b(por la|a la|cada|todas las) {f}s?\b", t)), None)
        if franja:
            hm = (recordatorios._FRANJAS[franja], 0)
    if hm is None:
        raise RutinaError("Dime a qué hora (p. ej. «todos los días a las 8:00» o «de lunes a viernes a las 7:30»).")
    return normalizar_horario({"tipo": "diaria", "hora": f"{hm[0]:02d}:{hm[1]:02d}", "dias": dias})


def normalizar_horario(h) -> dict:
    """Valida un horario (dict o texto en español) y lo deja en su forma canónica."""
    if isinstance(h, str):
        return interpretar_horario(h)
    if not isinstance(h, dict):
        raise RutinaError("Horario no válido.")
    if h.get("tipo") == "cada":
        try:
            n = int(h.get("horas"))
        except (TypeError, ValueError):
            raise RutinaError("Indica cada cuántas horas (número entero).") from None
        if not MIN_HORAS <= n <= MAX_HORAS:
            raise RutinaError(f"El intervalo debe estar entre {MIN_HORAS} y {MAX_HORAS} horas.")
        return {"tipo": "cada", "horas": n}
    if h.get("tipo") == "diaria":
        hora = avisos._hhmm(h.get("hora"), "")
        if not hora:
            raise RutinaError("La hora debe tener el formato HH:MM.")
        dias = h.get("dias") or []
        if not isinstance(dias, list) or not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in dias):
            raise RutinaError("Los días deben ser números del 0 (lunes) al 6 (domingo).")
        dias = sorted(set(dias))
        return {"tipo": "diaria", "hora": hora, "dias": [] if len(dias) == 7 else dias}
    raise RutinaError("El horario debe ser diario (a una hora) o cada N horas.")


def describir(h: dict) -> str:
    if h["tipo"] == "cada":
        return "cada hora" if h["horas"] == 1 else f"cada {h['horas']} horas"
    dias, hora = h["dias"], h["hora"]
    if not dias:
        return f"todos los días a las {hora}"
    if dias == [0, 1, 2, 3, 4]:
        return f"de lunes a viernes a las {hora}"
    if dias == [5, 6]:
        return f"los fines de semana a las {hora}"
    nombres = [_DIAS_PLURAL[d] for d in dias]
    lista = nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]
    return f"los {lista} a las {hora}"


def siguiente(h: dict, ref: datetime, previa: float | None = None) -> datetime:
    """Próxima ejecución estrictamente posterior a `ref`. «Cada N horas» sigue el ritmo de `previa`
    (sin deriva) y salta las que se perdieron; las diarias van a la misma hora local aunque cambie la hora."""
    ref = ref.astimezone(tiempo.zona())
    if h["tipo"] == "cada":
        paso = h["horas"] * 3600
        if previa is None:
            return ref + timedelta(seconds=paso)
        p = previa
        if p <= ref.timestamp():
            p += paso * (int((ref.timestamp() - p) // paso) + 1)
        return datetime.fromtimestamp(p, tiempo.zona())
    hh, mm = map(int, h["hora"].split(":"))
    for i in range(0, 9):
        d = ref.date() + timedelta(days=i)
        if h["dias"] and d.weekday() not in h["dias"]:
            continue
        c = recordatorios._local(d, hh, mm)
        if c > ref:
            return c
    raise RutinaError("No hay ningún día elegido.")  # no ocurre con un horario normalizado


# --- CRUD (siempre filtrado por el usuario) ------------------------------------------------------------------
def _fila(r) -> dict:
    h = json.loads(r["horario"])
    return {"id": r["id"], "user_id": r["user_id"], "nombre": r["nombre"], "prompt": r["prompt"], "agente": r["agente"], "canal": r["canal"],
            "horario": h, "descripcion": describir(h), "activa": bool(r["activa"]), "proxima": r["proxima"],
            "ultima": r["ultima"], "ultimo_estado": r["ultimo_estado"], "ultimo_texto": r["ultimo_texto"],
            "conv_id": r["conv_id"], "en_curso": r["id"] in _en_curso}


def _texto(v, maximo: int, campo: str) -> str:
    t = " ".join(str(v or "").split()) if campo == "nombre" else str(v or "").strip()
    if not t:
        raise RutinaError(f"Falta {'el nombre' if campo == 'nombre' else 'qué debe hacer ARIA'}.")
    if len(t) > maximo:
        raise RutinaError(f"{'El nombre' if campo == 'nombre' else 'El texto'} es demasiado largo (máximo {maximo}).")
    return t


def _validar(datos: dict, rol: str, actual: dict | None = None) -> dict:
    """Valida los campos recibidos (todos al crear; los que vengan al editar)."""
    out = {}
    if actual is None or "nombre" in datos:
        out["nombre"] = _texto(datos.get("nombre"), MAX_NOMBRE, "nombre")
    if actual is None or "prompt" in datos:
        out["prompt"] = _texto(datos.get("prompt"), MAX_PROMPT, "prompt")
    if actual is None or "agente" in datos:
        ag = str(datos.get("agente") or agentes.AUTO).strip().lower()
        if ag not in agentes.AGENTES:
            raise RutinaError("Ese agente no existe.")
        if not agentes.permitido(ag, rol):
            raise RutinaError(f"El agente «{agentes.obtener(ag).nombre}» es solo para administradores.")
        out["agente"] = ag
    if actual is None or "canal" in datos:
        canal = str(datos.get("canal") or "telegram").strip().lower()
        if canal not in CANALES:
            raise RutinaError("El canal debe ser telegram, push, ambos o web.")
        out["canal"] = canal
    if actual is None or "horario" in datos:
        out["horario"] = normalizar_horario(datos.get("horario"))
    if "activa" in datos:
        if not isinstance(datos["activa"], bool):
            raise RutinaError("«activa» debe ser verdadero o falso.")
        out["activa"] = datos["activa"]
    return out


def crear(uid: int, rol: str, datos: dict, ref: datetime | None = None) -> dict:
    ref = ref or tiempo.ahora()
    d = _validar(datos if isinstance(datos, dict) else {}, rol)
    prox = siguiente(d["horario"], ref).timestamp()
    with closing(db._con()) as con, con:
        if con.execute("SELECT COUNT(*) FROM rutinas WHERE user_id=?", (uid,)).fetchone()[0] >= MAX_POR_USUARIO:
            raise RutinaError(f"Ya tienes {MAX_POR_USUARIO} rutinas; borra alguna antes de crear otra.")
        rid = con.execute("INSERT INTO rutinas (user_id, nombre, prompt, agente, canal, horario, activa, proxima, creado) "
                          "VALUES (?,?,?,?,?,?,?,?,?)",
                          (uid, d["nombre"], d["prompt"], d["agente"], d["canal"], json.dumps(d["horario"]),
                           int(d.get("activa", True)), prox, time.time())).lastrowid
        return _fila(con.execute("SELECT * FROM rutinas WHERE id=?", (rid,)).fetchone())


def listar(uid: int) -> list:
    with closing(db._con()) as con:
        return [_fila(r) for r in con.execute("SELECT * FROM rutinas WHERE user_id=? ORDER BY id", (uid,))]


def obtener(uid: int, rid: int) -> dict | None:
    with closing(db._con()) as con:
        r = con.execute("SELECT * FROM rutinas WHERE id=? AND user_id=?", (rid, uid)).fetchone()
    return _fila(r) if r else None


def actualizar(uid: int, rol: str, rid: int, datos: dict, ref: datetime | None = None) -> dict | None:
    """Edita los campos que vengan (también pausar/reanudar con `activa`). None si no es suya."""
    actual = obtener(uid, rid)
    if not actual:
        return None
    d = _validar(datos if isinstance(datos, dict) else {}, rol, actual)
    if not d:
        return actual
    ref = ref or tiempo.ahora()
    horario = d.get("horario", actual["horario"])
    if "horario" in d or (d.get("activa") and not actual["activa"]):
        d["proxima"] = siguiente(horario, ref).timestamp()  # al reanudar no se recupera lo perdido
    if "horario" in d:
        d["horario"] = json.dumps(d["horario"])
    if "activa" in d:
        d["activa"] = int(d["activa"])
    campos = ", ".join(f"{k}=?" for k in d)
    with closing(db._con()) as con, con:
        con.execute(f"UPDATE rutinas SET {campos} WHERE id=? AND user_id=?", (*d.values(), rid, uid))
    return obtener(uid, rid)


def borrar(uid: int, rid: int) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM rutinas WHERE id=? AND user_id=?", (rid, uid)).rowcount > 0


def buscar(uid: int, consulta) -> list:
    q = str(consulta or "").strip().lstrip("#")
    if q.isdigit():
        r = obtener(uid, int(q))
        return [r] if r else []
    palabras = [p for p in recordatorios._norm(q).split() if len(p) > 2 and p not in ("rutina", "rutinas")]
    return [r for r in listar(uid) if palabras and all(p in recordatorios._norm(r["nombre"] + " " + r["prompt"])
                                                        for p in palabras)]


# --- Ejecución ------------------------------------------------------------------------------------------------
def _usuario(uid: int) -> dict | None:
    from . import usuarios
    u = usuarios.por_id(uid)
    return u if u and u["activo"] else None


def _guardar_resultado(rid: int, estado: str, texto: str, cid: str | None, ahora: float) -> None:
    with closing(db._con()) as con, con:
        con.execute("UPDATE rutinas SET ultima=?, ultimo_estado=?, ultimo_texto=?, conv_id=COALESCE(?, conv_id) "
                    "WHERE id=?", (ahora, estado, texto[:300], cid, rid))


def _guardar_conversacion(u: dict, r: dict, agente_id: str, texto: str, cerebro: str | None) -> str:
    """El resultado queda en una conversación «Rutina · nombre» (se puede seguir hablando de él). La de la
    ejecución anterior se borra si nadie escribió en ella; si el usuario siguió la charla, se conserva."""
    uid = u["id"]
    viejo = r.get("conv_id")
    if viejo:
        conv = db.obtener(viejo, uid)
        if conv and len(conv["mensajes"]) <= 2:
            db.borrar(viejo, uid)
    cid = db.crear(uid, f"Rutina · {r['nombre']}")
    db.fijar_agente(cid, uid, agente_id)
    db.anadir(cid, "user", r["prompt"])
    db.anadir(cid, "assistant", texto, cerebro, agente_id)
    return cid


async def _correr(u: dict, r: dict) -> tuple:
    """Pasa el prompt por el bucle del chat: solo nube y solo herramientas de consulta. (texto, cerebro, agente)."""
    from . import chat, memoria, tools
    ag, limpio, _motivo, _aviso = await chat.elegir_agente(u, r["agente"], r["prompt"])
    memoria.uid_actual.set(u["id"])
    acumulado, error, cerebro = "", None, None
    gen = chat.responder([{"role": "user", "content": limpio}], u["rol"], u["nombre"], agente=ag, uid=u["id"],
                         solo_nube=True, limite=tools.RUTINAS)
    try:
        async for ev in gen:
            t = ev.get("type")
            if t == "cerebro":
                cerebro = ev.get("etiqueta")
            elif t == "token":
                acumulado += ev["text"]
            elif t in ("reinicio", "herramienta"):
                acumulado = ""
            elif t == "error":
                error = ev.get("text")
    finally:
        await gen.aclose()
    if not acumulado.strip():
        raise RutinaError(error or "El cerebro no devolvió ninguna respuesta.")
    return acumulado.strip(), cerebro, ag.id


def _canales(canal: str) -> list:
    lista = {"telegram": ["telegram"], "push": ["push"], "ambos": ["telegram", "push"]}.get(canal, [])
    return [c for c in lista if c in avisos.canales()]


def _recortar(texto: str) -> str:
    if len(texto) <= MAX_RESULTADO:
        return texto
    corte = texto[:MAX_RESULTADO].rsplit("\n", 1)[0] if "\n" in texto[:MAX_RESULTADO] else texto[:MAX_RESULTADO]
    return corte.rstrip() + "\n\n… (sigue en el chat de ARIA)"


async def ejecutar(r: dict, canales_: list | None = None, ahora: float | None = None) -> dict:
    """Ejecuta una rutina ya y entrega el resultado. `canales_`: None = los de la rutina; [] = solo la campana.
    Devuelve {estado, texto}. Nunca lanza (todo fallo queda como estado «error» y aviso en la campana)."""
    from . import cerebros
    uid = r["user_id"] if "user_id" in r else None
    u = await asyncio.to_thread(_usuario, uid) if uid is not None else None
    if not u:
        return {"estado": "sin_usuario", "texto": ""}
    if r["id"] in _en_curso:
        return {"estado": "en_curso", "texto": "Esa rutina ya se está ejecutando."}
    _en_curso.add(r["id"])
    try:
        cid = None
        if not cerebros.hay_nube():
            estado = "sin_nube"
            texto = (f"La rutina «{r['nombre']}» no se ha ejecutado: ahora mismo solo responde el cerebro local "
                     "y las rutinas solo usan cerebros en la nube.")
        else:
            try:
                async with _sem:
                    res, cerebro, ag_id = await asyncio.wait_for(_correr(u, r), TIMEOUT_S)
                cid = await asyncio.to_thread(_guardar_conversacion, u, r, ag_id, res, cerebro)
                estado, texto = "ok", f"**Rutina «{r['nombre']}»**\n\n{_recortar(res)}"
            except asyncio.TimeoutError:
                estado, texto = "error", f"La rutina «{r['nombre']}» tardó demasiado (más de {TIMEOUT_S} s) y se canceló."
            except RutinaError as e:
                estado, texto = "error", f"La rutina «{r['nombre']}» no pudo completarse: {e}"
            except Exception:  # noqa: BLE001 - una rutina rota no debe tumbar el planificador
                log.exception("Falló la rutina %s", r["id"])
                estado, texto = "error", f"La rutina «{r['nombre']}» falló por un error interno."
        ahora = time.time() if ahora is None else ahora
        await asyncio.to_thread(_guardar_resultado, r["id"], estado, texto, cid, ahora)
        lista = _canales(r["canal"]) if canales_ is None else canales_
        await avisos.emitir("rutina", "info" if estado == "ok" else "aviso", texto, "ajustes", [uid],
                            ignorar_silencio=True, canales_=lista, extra={"rutina": r["id"]})
        return {"estado": estado, "texto": texto}
    finally:
        _en_curso.discard(r["id"])


def vencidas(ahora: float) -> list:
    with closing(db._con()) as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM rutinas WHERE activa=1 AND proxima IS NOT NULL AND proxima<=? ORDER BY proxima LIMIT 50",
            (ahora,))]


def _reservar(r: dict, ahora: float) -> bool:
    """Anota la ejecución programada (clave única en avisos_estado) y calcula la próxima, todo en una transacción.
    Devuelve False si esa ejecución ya estaba anotada (otro tick o un reinicio la cogió antes)."""
    clave = f"rutina:{r['id']}:{int(r['proxima'])}"
    prox = siguiente(json.loads(r["horario"]), datetime.fromtimestamp(ahora, tiempo.zona()), previa=r["proxima"])
    with closing(db._con()) as con, con:
        nueva = con.execute("INSERT OR IGNORE INTO avisos_estado (clave, chequeo, activo, desde) VALUES (?,?,0,?)",
                            (clave, "rutina", ahora)).rowcount > 0
        con.execute("UPDATE rutinas SET proxima=? WHERE id=? AND proxima=?", (prox.timestamp(), r["id"], r["proxima"]))
        con.execute("DELETE FROM avisos_estado WHERE chequeo='rutina' AND desde<?", (ahora - 14 * 86400,))
    return nueva


def _omitida(rid: int) -> None:
    with closing(db._con()) as con, con:
        con.execute("UPDATE rutinas SET ultimo_estado='omitida' WHERE id=?", (rid,))


async def disparar_vencidas(ahora: float | None = None, esperar: bool = False) -> list:
    """Lo llama el planificador de avisos. Las ejecuciones van en segundo plano (no frenan los chequeos);
    con `esperar=True` (pruebas) se esperan."""
    ahora = time.time() if ahora is None else ahora
    lanzadas = []
    for r in await asyncio.to_thread(vencidas, ahora):
        if not await asyncio.to_thread(_reservar, r, ahora):
            continue
        if ahora - r["proxima"] > VENTANA_S:
            log.info("Rutina %s atrasada (ARIA estaba apagada); se salta hasta la próxima", r["id"])
            await asyncio.to_thread(_omitida, r["id"])
            continue
        lanzadas.append(r["id"])
        if esperar:
            await ejecutar(r)
        else:
            en_segundo_plano(ejecutar(r))
    return lanzadas


def en_segundo_plano(coro) -> asyncio.Task:
    t = asyncio.create_task(coro)
    _tareas.add(t)
    t.add_done_callback(_tareas.discard)
    return t
