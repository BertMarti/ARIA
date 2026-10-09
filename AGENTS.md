# AGENTS.md

Guía para cualquier agente de programación (convención agents.md).

## Proyecto
ARIA 2.0: centro de control del laboratorio doméstico en Raspberry Pi (FastAPI + Ollama + Caddy, Docker Compose). Código en `app/aria/`, frontend sin build en `app/static/`, pruebas en `app/tests/`, proxy en `caddy/Caddyfile`. Scripts: `install.sh`, `update.sh`, `backup.sh`.

## Comandos
- Validar: `docker compose config`; pruebas: ver README (sección Pruebas); `node --check app/static/*.js`
- Levantar: `docker compose up -d --build` y `docker compose ps` (ollama, searxng, app, voz y caddy healthy; escaner en marcha)
- Comprobar: `curl -k https://<IP>/health`
- Logs: `docker compose logs -f app`

## Búsqueda en internet
Servicio `searxng` (`searxng/settings.yml`), cliente en `app/aria/busqueda.py`, herramientas `buscar_en_internet` y `noticias` en `tools.py`. Pruebas: `app/tests/test_busqueda.py` (SearXNG falso, sin red). No publiques puertos de SearXNG.

## Cerebros
Cadena de IA en `app/aria/cerebros.py` (Ollama Cloud → Groq → Gemini → local). Configuración en `.env` (`ARIA_CEREBROS`, `ARIA_MODELO_*`, claves) y `data/cerebros.json`. Pruebas en `app/tests/test_cerebros.py` con proveedores falsos. No imprimas claves ni las pongas en commits.

## Usuarios y SSO
Varios usuarios con rol `admin` o `usuario` (`app/aria/usuarios.py`, `permisos.py`) y SSO con Cloudflare Access (`sso.py`, `ARIA_CF_ACCESS_TEAM`, `ARIA_CF_ACCESS_AUD`, `ARIA_ADMIN_EMAILS`). Los permisos se imponen en el servidor con lista blanca; un endpoint nuevo es de admin salvo que se añada a `permisos.py`. Nunca confíes en la cabecera de email de Cloudflare: solo en el JWT verificado. No añadas tokens de la API de Cloudflare a ARIA. Pruebas: `test_sso.py`, `test_permisos.py`, `test_auth.py`.

## Voz
Contenedor `aria-voz` (`voz/`): faster-whisper (respaldo local), Piper (voz de ARIA) y Vosk (palabra «Aria»). La app (`app/aria/voz.py`) transcribe con Groq Whisper y, si falla, con `aria-voz`; el WebSocket `/api/voz/despertar` valida Origin, sesión y rol él mismo. Frontend en `app/static/voz.js` y `pcm-worklet.js`. Pruebas en `app/tests/test_voz.py` (sin red). El audio no se guarda nunca; la palabra de activación es «Aria».

## Visión
Imágenes en el chat (`/api/chat` con `imagen` en data URL) y en Telegram (fotos). Código en `app/aria/vision.py` (validación por bytes, ≤ 5 MB, limpieza de metadatos sin Pillow, Gemini → Groq; nunca el local) y `chat.conversar_imagen`. La imagen no se guarda nunca: el historial lleva «[imagen]». Los tickets se proponen y solo se apuntan al confirmar (`/api/vision/tickets/{token}` en la web, fichas `ticket` en Telegram) con `registrar_movimiento` y el uid de la sesión. Límite 6/min y 60/h por usuario. Pruebas sin red en `test_vision.py` (proveedores falsos, IDOR). No registres imágenes ni su texto.

## Memoria
Recuerdos y diario por usuario (`memoria.py`, `aprender.py`, `diario.py`, `briefing.py`). Aprender y resumir van en segundo plano y solo con cerebros de la nube. Todo acceso filtra por el usuario de la sesión; añade pruebas de IDOR si tocas esos endpoints. Un endpoint nuevo para `usuario` debe entrar en `permisos.py` y en `test_toda_ruta_registrada_esta_cubierta`.

## Agentes especializados
`app/aria/agentes.py` define ARIA, Finanzas, Redes y Seguridad (solo admin). Finanzas es por usuario (`uid` siempre del servidor). Seguridad usa el contenedor `aria-escaner` (`app/escaner/`), que solo escanea `ARIA_RED_PERMITIDA` (la red de casa, detectada por install.sh): uso defensivo, sin ataques ni fuerza bruta. Pruebas: `test_agentes.py`, `test_finanzas.py`, `test_seguridad.py`.

## Avisos, Telegram y push
Motor de avisos y planificador en `app/aria/avisos.py` (+ `avisos_chequeos.py`), recordatorios en `recordatorios.py`, bot de Telegram con long polling en `telegram.py` (sin webhook; fichas de botón en servidor ligadas a chat y usuario), Web Push en `push.py` y `static/sw.js`. Todo se filtra por el usuario de la sesión. Pruebas sin red: `test_avisos.py`, `test_recordatorios.py`, `test_telegram.py` (Bot API falsa), `test_push.py`. Autoprueba del bot: `docker compose exec app python -m aria.telegram --probar`.

## Rutinas
`app/aria/rutinas.py` (tabla `rutinas`, horario en español, `disparar_vencidas` desde `avisos.tick`, ejecución por `chat.responder(..., solo_nube=True, limite=tools.RUTINAS)`), API en `api_rutinas.py`, frontend `static/rutinas.js`. Una rutina solo usa herramientas de `tools.RUTINAS` (consultas): no añadas ahí nada que cambie la casa, los datos o la memoria. Antidisparos dobles: clave `rutina:<id>:<instante>` en `avisos_estado` antes de ejecutar. Lectura de enlaces anti-SSRF en `enlaces.py` (`resumir_enlace`): no relajes la comprobación de IP públicas ni sigas redirecciones sin revalidar. Paleta Ctrl+K en `static/paleta.js` y Web Share Target (`manifest.webmanifest` + `static/compartir.js`). Pruebas: `test_rutinas.py` (IDOR incluido), `test_enlaces.py`, `test_telegram.py`.
## Control parental
`app/aria/control.py` (estado en SQLite `control_*`, reconciliación con Pi-hole v6 por grupos `ARIA-pausa` y `ARIA-svc-*`, horarios, bucle de 30 s), `api_control.py` (`/api/red/control/...`, solo admin: no están en la lista blanca de `permisos.py`), cliente de grupos/clientes/dominios en `shield.py`, herramientas del agente Redes (`pausar_internet`, `reanudar_internet`, `bloquear_servicio`, `desbloquear_servicio`, `estado_control`), `/control` en `telegram.py`, aviso tipo `control` y `static/parental.js`. Reglas: solo dispositivos del inventario y nunca el router ni la Raspberry; ninguna acción «para todos»; ARIA solo modifica lo marcado con `ARIA-control:`; el cliente va siempre en `Default` además de sus grupos; es bloqueo por DNS y la interfaz debe decirlo. Las pruebas usan un Pi-hole falso (`httpx.MockTransport`, `test_control.py`); nunca escribas en el Pi-hole real (si hace falta, un grupo de prueba `aria-prueba-control` sin clientes reales y bórralo).

## Módulos
Extensiones enchufables en `modulos/<id>/` (montada `:ro` en `/srv/modulos`): `modulo.json` (validado de forma estricta en `app/aria/modulos.py`) y `modulo.py` opcional con `registrar(aria)` usando SOLO el SDK `app/aria/sdk.py` (`herramienta`, `chequeo`, `router`, `config`, `datos`, `comprobar_url`/`leer_url`, `log`). `ARIA_MODULOS` elige cuáles (vacío/`*` = todos, `-` = ninguno). Un módulo roto queda en «error» y se deshace lo que registró; nunca debe tumbar ARIA. Sus rutas son solo de admin salvo las declaradas para `usuario` (`permisos.permitir_modulo`, siempre bajo `/api/modulos/<id>/`); sus herramientas se registran con `tools.registrar_externa` (no chocan con `tools.NUCLEO`). SHIELD-DNS y HEIMDALL se listan como integradas (`modulos.INTEGRADOS`) pero su código sigue en el núcleo: no lo muevas. API `GET /api/modulos` (filtrada por rol, nunca valores de variables), `static/modulos.js` (mosaicos de Inicio y Ajustes → Módulos). Ejemplo `modulos/uptime`, plantilla `modulos/_plantilla`. Pruebas: `test_modulos.py` y `app/tests/modulos_prueba/` (main.py los carga en las pruebas vía `ARIA_MODULOS_DIR`). Guía: `docs/MODULOS.md`.

## Reglas
- Español (España) en UI, documentación, comentarios y commits.
- Sin secretos en el repo (`.env`, `data/` ignorados).
- Dependencias mínimas; sin build de frontend; salida del modelo solo como texto escapado.
- Respetar los puertos de otros proyectos: ARIA 80/443; SHIELD-DNS 53, 8080, 8443; HEIMDALL 51820/udp, 51843.
- Toda herramienta nueva necesita entrada en `_INTENCIONES` y pruebas; nunca exponer al modelo acciones destructivas.
- Nunca enviar claves privadas ni texto de la API/modelo al navegador vía `innerHTML`.
- Solo tocar contenedores `aria-*`. No hacer push sin revisión.
- La documentación debe describir solo lo que existe.
- Escaparate público (cuando exista): es lo único visible sin sesión. Solo datos inventados, todo estático y pregrabado (sin IA en vivo, formularios, analítica ni cookies), tipografías alojadas en ARIA y la misma CSP estricta.

## Trabajo con varios modelos (opcional, vía OpenCode)

Un agente orquestador (por ejemplo Claude en Claude Code) puede repartir tareas entre los modelos que tengas conectados en [OpenCode](https://opencode.ai): GitHub Copilot, ChatGPT, Gemini, modelos gratuitos de OpenCode Zen, etc. Así se ahorra cuota del modelo principal sin perder el control.

**Papeles**
- **Orquestador:** entiende la petición, planifica, divide en tareas pequeñas con rutas y objetivo concretos, revisa todo lo que vuelve, pasa las pruebas, hace commit y despliega. Es el único que hace commit, push o despliega.
- **Delegados:** reciben una tarea cerrada (escribir una función, redactar documentación, revisar un diff) y devuelven el resultado.

**Cómo delegar**
```bash
opencode models                    # modelos disponibles (proveedor/modelo)
opencode auth list                 # cuentas conectadas
# Revisión o consulta, sin tocar archivos:
opencode run --agent plan -m <proveedor/modelo> --dir <repo> "Revisa ... y lista los problemas"
# Cambios: siempre en un worktree aparte, nunca en la copia desplegada
git worktree add ../.wt/<tarea> -b feat/<tarea>
opencode run -m <proveedor/modelo> --dir ../.wt/<tarea> "Implementa ... siguiendo AGENTS.md"
```

**Reparto orientativo**
| Tarea | Modelo |
|---|---|
| Diseño, seguridad, depuración difícil, revisión final | El más capaz (orquestador) |
| Implementar funciones siguiendo un patrón existente | Modelo de código (Copilot / GPT) |
| Documentación, traducciones, textos | Modelo rápido (Gemini / Copilot) |
| Búsquedas, resúmenes, borradores sin datos sensibles | Modelos gratuitos (Zen) |

**Perfil restringido para delegados** (`~/.config/opencode/opencode.jsonc`). Usa una lista de comandos permitidos, no de prohibidos:
```jsonc
{
  "agent": {
    "delegado": {
      "mode": "primary",
      "permission": {
        "*": "deny", "read": "allow", "edit": "allow", "glob": "allow", "grep": "allow", "list": "allow",
        "webfetch": "allow", "external_directory": "deny",
        "bash": { "*": "deny", "ls *": "allow", "cat *": "allow", "grep *": "allow", "find *": "allow",
                  "git status*": "allow", "git diff*": "allow", "git log*": "allow",
                  "node --check *": "allow", "python3 -m py_compile *": "allow" }
      }
    }
  }
}
```
Se usa con `opencode run --agent delegado -m <modelo> --dir <worktree> "Lee TAREA.md y cúmplela; termina con INFORME.md"`. `TAREA.md` e `INFORME.md` están en `.gitignore`.

**Flujo por mejora:** encargo (`TAREA.md`) → implementa un modelo de código → revisa otro modelo en solo lectura → el orquestador corrige, pasa la suite completa, integra y despliega.

**Reglas**
- Nunca pases a un delegado secretos, `.env`, contraseñas ni datos personales. Con los modelos **gratuitos**, todavía menos: algunos usan lo que reciben para entrenar.
- Los delegados no hacen commit, push ni despliegues, ni tocan servicios en marcha. Las revisiones se hacen con `--agent plan` (solo lectura).
- Todo lo que devuelva un delegado lo revisa el orquestador y pasa la suite completa de pruebas antes de integrarse.
- Dale a cada delegado el contexto que necesita (rutas, este `AGENTS.md`, criterios de aceptación): no comparte la memoria del orquestador.
