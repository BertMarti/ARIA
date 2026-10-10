"""Motor de avisos: comprobaciones periódicas, avisos por usuario y entrega por los canales (Telegram, push).

Un planificador asyncio dentro de la propia app (sin contenedor nuevo) ejecuta cada `Chequeo` a su ritmo.
Cada chequeo devuelve la lista de problemas activos (`Problema`, con su clave de deduplicación) o None si
no puede saberlo (servicio sin configurar). El motor guarda el estado de cada clave en `avisos_estado`:

- chequeos de estado (servicio caído, disco lleno...): se avisa al activarse (tras `confirmaciones`
  comprobaciones seguidas, contra falsos positivos), como mucho una vez cada `cooldown_s` por clave,
  opcionalmente se recuerda cada `repetir_s`, y al resolverse se manda el «todo en orden» (`texto_ok`);
- chequeos de evento (dispositivo nuevo, hallazgo nuevo): cada clave se avisa una sola vez. Con
  `linea_base`, la primera pasada solo anota lo que ya existe (no se avisa de lo de siempre al instalar).

Los avisos se guardan en `avisos` (una fila por destinatario; `user_id` NULL al emitir = todos los
administradores) y se entregan por los canales que el usuario tenga activos, respetando sus horas de
silencio (salvo los graves y los recordatorios) y sus interruptores por tipo.
"""
import asyncio
import json
import logging
import time
from collections import deque
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, time as hora, timedelta
from typing import Awaitable, Callable

from . import config, db, tiempo

log = logging.getLogger("aria.avisos")

SEVERIDADES = ("info", "aviso", "grave")
TICK_S = 20
RETENCION_DIAS = 30
MAX_TEXTO = 600
TIMEOUT_CHEQUEO_S = 60

# Tipos de aviso que el usuario puede activar o desactivar: id -> (nombre, solo admin, activo por defecto)
TIPOS = {
    "servicios": ("SHIELD-DNS o HEIMDALL caídos", True, True),
    "tunel": ("Acceso desde fuera (túnel de Cloudflare) caído", True, True),
    "dispositivo_nuevo": ("Dispositivo desconocido en la red", True, True),
    "seguridad": ("Hallazgo grave en el escaneo de seguridad", True, True),
    "copia": ("Copia de seguridad fuera de casa atrasada", True, True),
    "sistema": ("Raspberry: temperatura, disco o RAM", True, True),
    "cerebros": ("Solo responde el cerebro local", True, True),
    "vpn_conexion": ("Un dispositivo se conecta a la VPN", True, False),
    "vpn_ubicacion": ("Conexión VPN desde un sitio nuevo", True, True),
    "control": ("Control parental: un horario empieza o termina", True, True),
    "informe_semanal": ("Informe semanal", True, True),
    "telemetria": ("Picos de CPU, temperatura o contenedores", True, True),
    "agenda": ("Eventos y cumpleaños de tu agenda", False, True),
}
# Tipos que no se pueden silenciar con los interruptores (los pide el propio usuario).
SIEMPRE = {"recordatorio", "prueba", "resumen", "rutina", "agenda"}


@dataclass
class Problema:
    clave: str
    texto: str
    severidad: str | None = None   # None = la del chequeo


@dataclass
class Chequeo:
    id: str
    tipo: str
    severidad: str
    fn: Callable[[], Awaitable[list | None]]
    intervalo_s: int = 60
    cooldown_s: int = 30 * 60        # mínimo entre dos avisos de la misma clave
    repetir_s: int | None = None     # recordar mientras siga activo (None = no)
    confirmaciones: int = 1          # comprobaciones seguidas antes de dar el problema por bueno
    texto_ok: str | Callable[[str], str] | None = None   # mensaje de «todo en orden» (None = en silencio)
    evento: bool = False
    linea_base: bool = False
    enlace: str = ""
    solo_admin: bool = True
    activo: bool = True


_CHEQUEOS: dict = {}
_rachas: dict = {}          # (chequeo, clave) -> comprobaciones seguidas con el problema
_ultima_ejecucion: dict = {}
_CANALES: dict = {}         # nombre -> async fn(uid, aviso: dict) -> bool


def registrar_chequeo(c: Chequeo) -> Chequeo:
    _CHEQUEOS[c.id] = c
    return c


def chequeos() -> dict:
    return dict(_CHEQUEOS)


def registrar_canal(nombre: str, fn) -> None:
    """Telegram y push se registran aquí al arrancar (así este módulo no depende de ellos)."""
    _CANALES[nombre] = fn


def canales() -> dict:
    return dict(_CANALES)


# --- Base de datos ----------------------------------------------------------------------------------
def iniciar() -> None:
    with closing(db._con()) as con, con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS avisos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES usuarios(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL, severidad TEXT NOT NULL CHECK (severidad IN ('info','aviso','grave')),
                texto TEXT NOT NULL, enlace TEXT NOT NULL DEFAULT '', creado REAL NOT NULL,
                leido INTEGER NOT NULL DEFAULT 0, entregado_por TEXT NOT NULL DEFAULT '');
            CREATE INDEX IF NOT EXISTS idx_avisos_user ON avisos(user_id, creado DESC);
            CREATE TABLE IF NOT EXISTS avisos_estado (
                clave TEXT PRIMARY KEY, chequeo TEXT NOT NULL, activo INTEGER NOT NULL DEFAULT 0,
                desde REAL, ultimo_envio REAL, avisado INTEGER NOT NULL DEFAULT 0, texto TEXT);
            CREATE INDEX IF NOT EXISTS idx_avisos_estado ON avisos_estado(chequeo, activo);
            CREATE TABLE IF NOT EXISTS avisos_ajustes (
                user_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE, datos TEXT NOT NULL);
        """)


# --- Ajustes por usuario ------------------------------------------------------------------------------
def ajustes_defecto() -> dict:
    return {"tipos": {t: d for t, (_, _, d) in TIPOS.items()},
            "silencio": {"activo": True, "desde": "23:00", "hasta": "08:00"},
            "canales": {"telegram": True, "push": True},
            "briefing": {"activo": True, "hora": "08:00", "canal": "telegram", "voz": True},
            "informe": {"activo": True, "dia": 6, "hora": "20:00", "canal": "telegram"},
            "voz_telegram": False}


def _hhmm(v, defecto: str) -> str:
    if isinstance(v, str) and len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit():
        if int(v[:2]) < 24 and int(v[3:]) < 60:
            return v
    return defecto


def normalizar_ajustes(d) -> dict:
    """Mezcla lo recibido con los valores por defecto y descarta todo lo que no sea válido."""
    base = ajustes_defecto()
    d = d if isinstance(d, dict) else {}
    tipos = d.get("tipos") if isinstance(d.get("tipos"), dict) else {}
    for t in base["tipos"]:
        if isinstance(tipos.get(t), bool):
            base["tipos"][t] = tipos[t]
    s = d.get("silencio") if isinstance(d.get("silencio"), dict) else {}
    if isinstance(s.get("activo"), bool):
        base["silencio"]["activo"] = s["activo"]
    base["silencio"]["desde"] = _hhmm(s.get("desde"), base["silencio"]["desde"])
    base["silencio"]["hasta"] = _hhmm(s.get("hasta"), base["silencio"]["hasta"])
    c = d.get("canales") if isinstance(d.get("canales"), dict) else {}
    for k in base["canales"]:
        if isinstance(c.get(k), bool):
            base["canales"][k] = c[k]
    b = d.get("briefing") if isinstance(d.get("briefing"), dict) else {}
    if isinstance(b.get("activo"), bool):
        base["briefing"]["activo"] = b["activo"]
    base["briefing"]["hora"] = _hhmm(b.get("hora"), base["briefing"]["hora"])
    if b.get("canal") in ("telegram", "push", "ambos"):
        base["briefing"]["canal"] = b["canal"]
    if isinstance(b.get("voz"), bool):
        base["briefing"]["voz"] = b["voz"]
    i = d.get("informe") if isinstance(d.get("informe"), dict) else {}
    if isinstance(i.get("activo"), bool):
        base["informe"]["activo"] = i["activo"]
    if isinstance(i.get("dia"), int) and not isinstance(i["dia"], bool) and 0 <= i["dia"] <= 6:
        base["informe"]["dia"] = i["dia"]
    base["informe"]["hora"] = _hhmm(i.get("hora"), base["informe"]["hora"])
    if i.get("canal") in ("telegram", "push", "ambos"):
        base["informe"]["canal"] = i["canal"]
    if isinstance(d.get("voz_telegram"), bool):
        base["voz_telegram"] = d["voz_telegram"]
    return base


def ajustes(uid: int) -> dict:
    with closing(db._con()) as con:
        r = con.execute("SELECT datos FROM avisos_ajustes WHERE user_id=?", (uid,)).fetchone()
    try:
        return normalizar_ajustes(json.loads(r["datos"]) if r else {})
    except ValueError:
        return ajustes_defecto()


def guardar_ajustes(uid: int, datos) -> dict:
    a = normalizar_ajustes(datos)
    with closing(db._con()) as con, con:
        con.execute("INSERT INTO avisos_ajustes (user_id, datos) VALUES (?,?) "
                    "ON CONFLICT(user_id) DO UPDATE SET datos=excluded.datos", (uid, json.dumps(a)))
    return a


def tipos_para(rol: str) -> list:
    return [{"id": t, "nombre": n} for t, (n, solo_admin, _) in TIPOS.items() if rol == "admin" or not solo_admin]


def _minutos(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def en_silencio(a: dict, ref: datetime | None = None) -> bool:
    """¿Es hora de silencio para este usuario? El tramo puede cruzar la medianoche (23:00–08:00)."""
    s = a["silencio"]
    if not s["activo"]:
        return False
    n = (ref.astimezone(tiempo.zona()) if ref else tiempo.ahora())
    m, ini, fin = n.hour * 60 + n.minute, _minutos(s["desde"]), _minutos(s["hasta"])
    if ini == fin:
        return False
    return ini <= m < fin if ini < fin else (m >= ini or m < fin)


# --- Usuarios destinatarios -----------------------------------------------------------------------------
def _usuarios_activos() -> list:
    from . import usuarios
    return [u for u in usuarios.listar() if u["activo"]]


def admins() -> list:
    return [u["id"] for u in _usuarios_activos() if u["rol"] == "admin"]


def _rol(uid: int) -> str | None:
    from . import usuarios
    u = usuarios.por_id(uid)
    return u["rol"] if u and u["activo"] else None


# --- Emitir y entregar ------------------------------------------------------------------------------------
def _insertar(uid: int, tipo: str, severidad: str, texto: str, enlace: str) -> int:
    with closing(db._con()) as con, con:
        return con.execute("INSERT INTO avisos (user_id, tipo, severidad, texto, enlace, creado) VALUES (?,?,?,?,?,?)",
                           (uid, tipo, severidad, texto, enlace, time.time())).lastrowid


def _marcar_entregado(aid: int, canales_: list) -> None:
    with closing(db._con()) as con, con:
        con.execute("UPDATE avisos SET entregado_por=? WHERE id=?", (",".join(canales_), aid))


async def emitir(tipo: str, severidad: str, texto: str, enlace: str = "", destinatarios: list | None = None,
                 ignorar_silencio: bool = False, guardar: bool = True, canales_: list | None = None,
                 extra: dict | None = None, ref: datetime | None = None) -> list:
    """Crea el aviso para cada destinatario (None = administradores activos) y lo entrega.

    Devuelve [{uid, id, canales}] con lo que se hizo. `guardar=False` no lo apunta en la campana (resumen de
    buenos días). `canales_` limita los canales (por defecto los que el usuario tiene activos)."""
    if severidad not in SEVERIDADES:
        severidad = "aviso"
    # El hook es deliberadamente después de validar el aviso y fuera de la entrega.
    # Las acciones pasan `automatizacion=True` para no crear cascadas.
    if not (extra or {}).get("automatizacion"):
        try:
            from . import automatizaciones
            await automatizaciones.evento(tipo, {"tipo": tipo, "texto": texto, **(extra or {})})
        except Exception:  # noqa: BLE001 - una regla rota no debe afectar a los avisos
            log.exception("Falló el hook de automatizaciones")
    texto = " ".join(str(texto).split())[:MAX_TEXTO] if "\n" not in str(texto) else str(texto).strip()[:MAX_TEXTO * 3]
    if destinatarios is None:
        destinatarios = await asyncio.to_thread(admins)
    hechos = []
    for uid in dict.fromkeys(destinatarios):
        rol = await asyncio.to_thread(_rol, uid)
        if rol is None:
            continue
        if tipo in TIPOS and TIPOS[tipo][1] and rol != "admin":
            continue  # avisos de administración: solo a administradores
        a = await asyncio.to_thread(ajustes, uid)
        if tipo in TIPOS and not a["tipos"].get(tipo, True):
            continue
        aid = await asyncio.to_thread(_insertar, uid, tipo, severidad, texto, enlace) if guardar else None
        usados = []
        silencio = not ignorar_silencio and severidad != "grave" and en_silencio(a, ref)
        if not silencio:
            for nombre, fn in _CANALES.items():
                if (canales_ is not None and nombre not in canales_) or (canales_ is None and not a["canales"].get(nombre, True)):
                    continue
                aviso = {"id": aid, "uid": uid, "tipo": tipo, "severidad": severidad, "texto": texto,
                         "enlace": enlace, **(extra or {})}
                try:
                    if await fn(uid, aviso):
                        usados.append(nombre)
                except Exception:  # noqa: BLE001 - un canal roto no debe impedir los demás
                    log.exception("No se pudo entregar el aviso por %s", nombre)
        if aid is not None:
            await asyncio.to_thread(_marcar_entregado, aid, ["web"] + usados)
        hechos.append({"uid": uid, "id": aid, "canales": usados, "silencio": silencio})
    return hechos


# --- Campana (API) --------------------------------------------------------------------------------------------
def _fila(r) -> dict:
    return {"id": r["id"], "tipo": r["tipo"], "severidad": r["severidad"], "texto": r["texto"],
            "enlace": r["enlace"], "creado": r["creado"], "leido": bool(r["leido"]),
            "entregado_por": [c for c in (r["entregado_por"] or "").split(",") if c]}


def listar(uid: int, limite: int = 50) -> dict:
    with closing(db._con()) as con:
        filas = con.execute("SELECT * FROM avisos WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limite)).fetchall()
        n = con.execute("SELECT COUNT(*) FROM avisos WHERE user_id=? AND leido=0", (uid,)).fetchone()[0]
    return {"avisos": [_fila(r) for r in filas], "no_leidos": n}


def no_leidos(uid: int) -> int:
    with closing(db._con()) as con:
        return con.execute("SELECT COUNT(*) FROM avisos WHERE user_id=? AND leido=0", (uid,)).fetchone()[0]


def marcar_leido(uid: int, aid: int) -> bool:
    with closing(db._con()) as con, con:
        return con.execute("UPDATE avisos SET leido=1 WHERE id=? AND user_id=?", (aid, uid)).rowcount > 0


def marcar_todos(uid: int) -> int:
    with closing(db._con()) as con, con:
        return con.execute("UPDATE avisos SET leido=1 WHERE user_id=? AND leido=0", (uid,)).rowcount


def purgar(dias: int = RETENCION_DIAS) -> int:
    with closing(db._con()) as con, con:
        return con.execute("DELETE FROM avisos WHERE creado<?", (time.time() - dias * 86400,)).rowcount


# --- Estado de los chequeos ---------------------------------------------------------------------------------
def _estado(con, clave: str):
    return con.execute("SELECT * FROM avisos_estado WHERE clave=?", (clave,)).fetchone()


def _hay_base(c: Chequeo) -> bool:
    with closing(db._con()) as con:
        return _estado(con, f"{c.id}:__base__") is not None


def _destinatarios_con_tipo(tipo: str) -> list:
    out = []
    for u in _usuarios_activos():
        if TIPOS.get(tipo, ("", True, True))[1] and u["rol"] != "admin":
            continue
        if ajustes(u["id"])["tipos"].get(tipo, True):
            out.append(u["id"])
    return out


async def procesar(c: Chequeo, problemas: list | None, ahora: float | None = None) -> list:
    """Aplica deduplicación, confirmaciones, cooldown y «todo en orden». Devuelve los textos emitidos."""
    if problemas is None:
        return []
    ahora = time.time() if ahora is None else ahora
    emitidos: list = []
    destinatarios = None if c.solo_admin else [u["id"] for u in await asyncio.to_thread(_usuarios_activos)]
    activos = {p.clave: p for p in problemas}

    def _sql(fn):
        with closing(db._con()) as con, con:
            return fn(con)

    primera = c.linea_base and not await asyncio.to_thread(_hay_base, c)
    if primera:
        def base(con):
            con.execute("INSERT OR IGNORE INTO avisos_estado (clave, chequeo, activo, desde) VALUES (?,?,1,?)",
                        (f"{c.id}:__base__", c.id, ahora))
            for p in problemas:
                con.execute("INSERT OR REPLACE INTO avisos_estado (clave, chequeo, activo, desde, ultimo_envio, avisado, texto) "
                            "VALUES (?,?,1,?,NULL,0,?)", (f"{c.id}:{p.clave}", c.id, ahora, p.texto))
        await asyncio.to_thread(_sql, base)
        return []

    for p in problemas:
        clave = f"{c.id}:{p.clave}"
        if not c.evento:
            _rachas[(c.id, p.clave)] = _rachas.get((c.id, p.clave), 0) + 1
            if _rachas[(c.id, p.clave)] < c.confirmaciones:
                continue
        fila = await asyncio.to_thread(_sql, lambda con, k=clave: _estado(con, k))
        enviar = False
        if c.evento:
            enviar = fila is None
        elif fila is None or not fila["activo"]:
            enviar = fila is None or fila["ultimo_envio"] is None or ahora - fila["ultimo_envio"] >= c.cooldown_s
        elif c.repetir_s and fila["ultimo_envio"] is not None and ahora - fila["ultimo_envio"] >= c.repetir_s:
            enviar = True

        def guardar(con, k=clave, p=p, enviar=enviar, fila=fila):
            nuevo_activo = fila is None or not fila["activo"]
            con.execute(
                "INSERT INTO avisos_estado (clave, chequeo, activo, desde, ultimo_envio, avisado, texto) VALUES (?,?,1,?,?,?,?) "
                "ON CONFLICT(clave) DO UPDATE SET activo=1, desde=CASE WHEN ? THEN excluded.desde ELSE desde END, "
                "ultimo_envio=CASE WHEN ? THEN excluded.ultimo_envio ELSE ultimo_envio END, "
                "avisado=CASE WHEN ? THEN 1 WHEN ? THEN 0 ELSE avisado END, texto=excluded.texto",
                (k, c.id, ahora, ahora if enviar else None, int(enviar), p.texto,
                 nuevo_activo, enviar, enviar, nuevo_activo))
        await asyncio.to_thread(_sql, guardar)
        if enviar:
            emitidos.append(p.texto)
            await emitir(c.tipo, p.severidad or c.severidad, p.texto, c.enlace, destinatarios,
                         extra={"dispositivo": p.clave if c.tipo in ("dispositivo_nuevo", "vpn_conexion") else None,
                                "dispositivo_desconocido": c.tipo == "dispositivo_nuevo"})

    if not c.evento:
        # Claves que ya no están activas: se resuelven (y se avisa si se había avisado del problema).
        def resueltas(con):
            filas = con.execute("SELECT * FROM avisos_estado WHERE chequeo=? AND activo=1 AND clave NOT LIKE ?",
                                (c.id, f"{c.id}:__base__")).fetchall()
            out = []
            for f in filas:
                corta = f["clave"][len(c.id) + 1:]
                if corta in activos:
                    continue  # sigue activo (o aún sin confirmar): no se toca
                con.execute("UPDATE avisos_estado SET activo=0 WHERE clave=?", (f["clave"],))
                out.append((corta, bool(f["avisado"])))
            return out
        for corta, avisado in await asyncio.to_thread(_sql, resueltas):
            if avisado and c.texto_ok:
                t = c.texto_ok(corta) if callable(c.texto_ok) else c.texto_ok
                emitidos.append(t)
                await emitir(c.tipo, "info", t, c.enlace, destinatarios)
        for k in [k for k in _rachas if k[0] == c.id and k[1] not in activos]:
            _rachas.pop(k, None)
    return emitidos


async def ejecutar_chequeo(c: Chequeo, ahora: float | None = None) -> list:
    if c.tipo in TIPOS and not TIPOS[c.tipo][2]:
        # Tipos apagados por defecto (VPN): solo se comprueban si alguien los quiere recibir.
        if not await asyncio.to_thread(_destinatarios_con_tipo, c.tipo):
            return []
    try:
        problemas = await asyncio.wait_for(c.fn(), TIMEOUT_CHEQUEO_S)
    except asyncio.TimeoutError:
        log.warning("El chequeo %s tardó demasiado", c.id)
        return []
    return await procesar(c, problemas, ahora)


# --- Planificador -----------------------------------------------------------------------------------------------
_ultimo_purgado = 0.0
_ultimas_propuestas = 0.0


async def tick(ahora: float | None = None) -> None:
    """Una vuelta del planificador: chequeos que tocan, recordatorios y rutinas vencidos y resumen de buenos días."""
    global _ultimo_purgado
    from . import recordatorios
    ahora = time.time() if ahora is None else ahora
    for c in list(_CHEQUEOS.values()):
        if not c.activo or ahora - _ultima_ejecucion.get(c.id, 0) < c.intervalo_s:
            continue
        _ultima_ejecucion[c.id] = ahora
        try:
            await ejecutar_chequeo(c, ahora)
        except Exception:  # noqa: BLE001 - un chequeo roto no para a los demás
            log.exception("Falló el chequeo %s", c.id)
    try:
        await recordatorios.disparar_vencidos(ahora)
    except Exception:  # noqa: BLE001
        log.exception("Falló el disparo de recordatorios")
    try:
        from . import agenda
        await agenda.disparar_avisos(ahora)
    except Exception:  # noqa: BLE001
        log.exception("Falló el disparo de agenda")
    try:
        from . import rutinas
        await rutinas.disparar_vencidas(ahora)
    except Exception:  # noqa: BLE001
        log.exception("Falló el disparo de rutinas")
    try:
        from . import automatizaciones
        await automatizaciones.tick(ahora)
    except Exception:  # noqa: BLE001
        log.exception("Falló el disparo de automatizaciones")
    try:
        await briefings_programados()
    except Exception:  # noqa: BLE001
        log.exception("Falló el resumen de buenos días programado")
    try:
        await informes_semanales_programados()
    except Exception:  # noqa: BLE001
        log.exception("Falló el informe semanal programado")
    global _ultimas_propuestas
    if ahora - _ultimas_propuestas >= 300:   # proactividad con permiso: cada 5 minutos
        _ultimas_propuestas = ahora
        try:
            from . import propuestas
            await propuestas.ciclo()
        except Exception:  # noqa: BLE001
            log.exception("Falló el ciclo de propuestas")
    try:   # accesos de invitados caducados: se desactivan y salen del grupo de Cloudflare
        from . import api_acceso
        for uid in await api_acceso.caducar_vencidos():
            log.info("Acceso de invitado caducado (usuario %s)", uid)
    except Exception:  # noqa: BLE001
        log.exception("Falló la caducidad de accesos de invitados")
    if ahora - _ultimo_purgado > 86400:
        _ultimo_purgado = ahora
        await asyncio.to_thread(purgar)


async def bucle(retraso: float = 30) -> None:
    await asyncio.sleep(retraso)
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Fallo en el planificador de avisos")
        await asyncio.sleep(TICK_S)


# --- Resumen de buenos días por Telegram / push ---------------------------------------------------------------
VENTANA_BRIEFING_S = 3 * 3600


def _ya_enviado(clave: str) -> bool:
    with closing(db._con()) as con:
        return _estado(con, clave) is not None


def _anotar_enviado(clave: str) -> None:
    with closing(db._con()) as con, con:
        con.execute("INSERT OR IGNORE INTO avisos_estado (clave, chequeo, activo, desde) VALUES (?,?,0,?)",
                    (clave, "briefing", time.time()))
        con.execute("DELETE FROM avisos_estado WHERE chequeo='briefing' AND desde<?", (time.time() - 7 * 86400,))


def briefing_toca(a: dict, ref: datetime) -> bool:
    """¿Está dentro de la ventana (hora elegida + 3 h) del resumen de hoy?"""
    if not a["briefing"]["activo"]:
        return False
    hh, mm = map(int, a["briefing"]["hora"].split(":"))
    objetivo = datetime.combine(ref.date(), hora(hh, mm), tzinfo=tiempo.zona())
    return timedelta(0) <= ref - objetivo < timedelta(seconds=VENTANA_BRIEFING_S)


_tareas_voz: set = set()   # referencias a las tareas de voz en curso (si no, el recolector podría cortarlas)


async def briefings_programados(ref: datetime | None = None) -> list:
    from . import briefing
    ref = (ref.astimezone(tiempo.zona()) if ref else tiempo.ahora())
    enviados = []
    for u in await asyncio.to_thread(_usuarios_activos):
        a = await asyncio.to_thread(ajustes, u["id"])
        clave = f"briefing:{u['id']}:{ref.date().isoformat()}"
        if not briefing_toca(a, ref) or await asyncio.to_thread(_ya_enviado, clave):
            continue
        canal = a["briefing"]["canal"]
        lista = ["telegram", "push"] if canal == "ambos" else [canal]
        lista = [c for c in lista if c in _CANALES]
        if not lista:
            continue
        await asyncio.to_thread(_anotar_enviado, clave)  # antes de enviar: si falla, no se repite cada 20 s
        try:
            from . import resumen_diario
            from . import invitados
            d = await resumen_diario.construir_resumen_diario(u, refrescar=True)
            d = invitados.recortar_resumen(d, await asyncio.to_thread(invitados.de, u["id"]))
            texto, html_tg = resumen_diario.texto_plano(d), resumen_diario.telegram(d)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo preparar el resumen de %s", u["id"])
            continue
        # Push recibe el texto plano; Telegram, el HTML completo (en `extra`, sin recortar a mitad de etiqueta)
        await emitir("resumen", "info", texto, "inicio", [u["id"]], ignorar_silencio=True, guardar=False, canales_=lista,
                     extra={"html": html_tg})
        if "telegram" in lista and a["briefing"]["voz"]:   # y debajo, el briefing hablado (en segundo plano: tarda)
            from . import telegram
            t = asyncio.create_task(telegram.briefing_voz_a_usuario(u))
            _tareas_voz.add(t)
            t.add_done_callback(_tareas_voz.discard)
        enviados.append(u["id"])
    return enviados


async def informes_semanales_programados(ref: datetime | None = None) -> list:
    """Envía una vez por semana el informe configurado por cada administrador."""
    from . import estadisticas
    ref = (ref.astimezone(tiempo.zona()) if ref else tiempo.ahora())
    enviados = []
    iso = ref.isocalendar()
    semana = f"{iso.year}-W{iso.week:02d}"
    for u in await asyncio.to_thread(_usuarios_activos):
        if u["rol"] != "admin":
            continue
        a = await asyncio.to_thread(ajustes, u["id"])
        i = a["informe"]
        hh, mm = map(int, i["hora"].split(":"))
        if not i["activo"] or ref.weekday() != i["dia"] or (ref.hour, ref.minute) < (hh, mm):
            continue
        clave = f"informe_semanal:{u['id']}:{semana}"
        if await asyncio.to_thread(_ya_enviado, clave):
            continue
        canales_ = ["telegram", "push"] if i["canal"] == "ambos" else [i["canal"]]
        canales_ = [c for c in canales_ if c in _CANALES]
        if not canales_:
            continue
        await asyncio.to_thread(_anotar_enviado, clave)
        try:
            texto = await estadisticas.construir_informe_semanal(ref.timestamp())
            await emitir("informe_semanal", "info", texto, "red", [u["id"]], ignorar_silencio=True,
                          canales_=canales_)
            enviados.append(u["id"])
        except Exception:  # noqa: BLE001
            log.exception("No se pudo preparar el informe semanal")
    return enviados


# --- Limitador sencillo (ventana deslizante en memoria) --------------------------------------------------------
class Limitador:
    def __init__(self, n: int, ventana: float, reloj=time.monotonic):
        self.n, self.ventana, self.reloj = n, ventana, reloj
        self._usos: dict = {}

    def permitir(self, clave) -> bool:
        ahora = self.reloj()
        q = self._usos.setdefault(clave, deque())
        while q and ahora - q[0] >= self.ventana:
            q.popleft()
        if len(q) >= self.n:
            return False
        q.append(ahora)
        return True
