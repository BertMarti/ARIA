"""Plantilla de módulo de ARIA (cópiala; el cargador ignora las carpetas que empiezan por «_»).

ARIA importa este archivo y llama a `registrar(aria)` una vez al arrancar. `aria` es el SDK (app/aria/sdk.py):
lo único del núcleo que deberías usar. Todo lo que registres aquí se valida y solo se aplica si `registrar`
termina sin errores; si algo falla, el módulo queda en «error» en Ajustes → Módulos y ARIA sigue funcionando.

AVISO: un módulo es código Python que corre DENTRO de ARIA, con sus permisos. Instala solo módulos de confianza.

Puedes partir el código en varios archivos de esta carpeta e importarlos con `from . import otro`.
"""
import time

_ARRANQUE = time.time()


def registrar(aria):
    # Variables de entorno: SOLO las declaradas en «env» o «env_opcional» del modulo.json.
    # Las de «env» siempre existen aquí (si faltasen, este archivo ni se ejecutaría).
    token = aria.config("PLANTILLA_TOKEN")
    saludo = aria.config("PLANTILLA_SALUDO", "¡Hola desde la plantilla!")
    aria.log.info("Plantilla lista (token de %d caracteres)", len(token))  # nunca escribas secretos en el log

    # ------------------------------------------------------------------------------------------------------------
    # 1) Herramienta del chat (solo lectura). El modelo la llama con los parámetros que declares.
    #    - nombre: minúsculas y _, único (no puede coincidir con una herramienta del núcleo).
    #    - intenciones: expresiones regulares sobre el mensaje en minúsculas. El modelo LOCAL solo recibe la
    #      herramienta si se cumple alguna (una cadena = basta con ella; una tupla = deben cumplirse todas;
    #      «!patrón» = NO debe aparecer). Las nubes reciben todas las permitidas.
    #    - solo_lectura=True: no cambia nada, así que también vale para las rutinas programadas.
    #    - roles: quién puede usarla (admin siempre). agentes: qué agentes la ofrecen ("aria" = el general).
    #    - Debe ser async y devolver texto (o algo serializable a JSON). `raise aria.Error("...")` manda ese
    #      texto tal cual al modelo; cualquier otra excepción se resume como «Error al ejecutar la herramienta».
    # ------------------------------------------------------------------------------------------------------------
    @aria.herramienta(
        "plantilla_saludo",
        "Devuelve un saludo de la plantilla y cuánto tiempo lleva cargado el módulo.",
        {"nombre": ("string", "A quién saludar (opcional)")},
        solo_lectura=True,
        roles=("admin", "usuario"),
        intenciones=[r"\bplantilla\b", (r"\bsaluda\w*\b", r"\bm[oó]dulo\b")],
    )
    async def plantilla_saludo(nombre: str = "") -> str:
        minutos = int((time.time() - _ARRANQUE) // 60)
        return f"{saludo} {nombre}".strip() + f" (módulo cargado hace {minutos} min)."

    # ------------------------------------------------------------------------------------------------------------
    # 2) Chequeo de avisos: el motor lo llama cada `intervalo_min` minutos. Devuelve:
    #    - [] si todo va bien;
    #    - una lista de problemas activos: aria.Problema(clave, texto) (o solo textos) — la clave identifica
    #      el problema para no repetir el aviso;
    #    - None si no se puede saber (p. ej. la aplicación no está configurada).
    #    Llega por Telegram/push a los administradores (para_todos=True: a todos), tras `confirmaciones`
    #    comprobaciones seguidas, y con `texto_ok` cuando se resuelve. En Ajustes → Avisos aparece el
    #    interruptor «Módulo <nombre>».
    # ------------------------------------------------------------------------------------------------------------
    @aria.chequeo("disco-lleno", intervalo_min=10, severidad="aviso", confirmaciones=2,
                  texto_ok="La plantilla vuelve a estar bien.")
    async def disco_lleno():
        libre = 100  # aquí consultarías tu aplicación (con httpx y un timeout corto, por ejemplo)
        if libre < 10:
            return [aria.Problema("disco", f"A la plantilla le queda poco disco ({libre} %).")]
        return []

    # ------------------------------------------------------------------------------------------------------------
    # 3) Endpoints: aria.router() devuelve un APIRouter de FastAPI colgado de /api/modulos/<id>.
    #    TODAS sus rutas son solo para admin, salvo las que declares en `usuario`. Sin sesión, 401; un
    #    usuario sin permiso, 403 (lo impone el servidor). Las peticiones que cambian algo (POST...) ya pasan
    #    por la comprobación CSRF de ARIA. No se admiten WebSocket.
    # ------------------------------------------------------------------------------------------------------------
    r = aria.router(usuario=[("GET", "/estado")])

    @r.get("/estado")          # GET /api/modulos/plantilla/estado  (admin y usuario)
    async def estado():
        return {"ok": True, "cargado_hace_s": int(time.time() - _ARRANQUE)}

    @r.post("/reiniciar")      # POST /api/modulos/plantilla/reiniciar  (solo admin)
    async def reiniciar():
        global _ARRANQUE
        _ARRANQUE = time.time()
        return {"ok": True}
