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
`app/aria/agentes.py` define ARIA, Finanzas, Redes y Seguridad (solo admin). Finanzas es por usuario (`uid` siempre del servidor). Seguridad usa el contenedor `aria-escaner` (`app/escaner/`), que solo escanea `ARIA_RED_PERMITIDA` (192.168.0.0/24): uso defensivo, sin ataques ni fuerza bruta. Pruebas: `test_agentes.py`, `test_finanzas.py`, `test_seguridad.py`.

## Avisos, Telegram y push
Motor de avisos y planificador en `app/aria/avisos.py` (+ `avisos_chequeos.py`), recordatorios en `recordatorios.py`, bot de Telegram con long polling en `telegram.py` (sin webhook; fichas de botón en servidor ligadas a chat y usuario), Web Push en `push.py` y `static/sw.js`. Todo se filtra por el usuario de la sesión. Pruebas sin red: `test_avisos.py`, `test_recordatorios.py`, `test_telegram.py` (Bot API falsa), `test_push.py`. Autoprueba del bot: `docker compose exec app python -m aria.telegram --probar`.

## Control parental
`app/aria/control.py` (estado en SQLite `control_*`, reconciliación con Pi-hole v6 por grupos `ARIA-pausa` y `ARIA-svc-*`, horarios, bucle de 30 s), `api_control.py` (`/api/red/control/...`, solo admin: no están en la lista blanca de `permisos.py`), cliente de grupos/clientes/dominios en `shield.py`, herramientas del agente Redes (`pausar_internet`, `reanudar_internet`, `bloquear_servicio`, `desbloquear_servicio`, `estado_control`), `/control` en `telegram.py`, aviso tipo `control` y `static/parental.js`. Reglas: solo dispositivos del inventario y nunca el router ni la Raspberry; ninguna acción «para todos»; ARIA solo modifica lo marcado con `ARIA-control:`; el cliente va siempre en `Default` además de sus grupos; es bloqueo por DNS y la interfaz debe decirlo. Las pruebas usan un Pi-hole falso (`httpx.MockTransport`, `test_control.py`); nunca escribas en el Pi-hole real (si hace falta, un grupo de prueba `aria-prueba-control` sin clientes reales y bórralo).

## Reglas
- Español (España) en UI, documentación, comentarios y commits.
- Sin secretos en el repo (`.env`, `data/` ignorados).
- Dependencias mínimas; sin build de frontend; salida del modelo solo como texto escapado.
- Respetar los puertos de otros proyectos: ARIA 80/443; SHIELD-DNS 53, 8080, 8443; HEIMDALL 51820/udp, 51843.
- Toda herramienta nueva necesita entrada en `_INTENCIONES` y pruebas; nunca exponer al modelo acciones destructivas.
- Nunca enviar claves privadas ni texto de la API/modelo al navegador vía `innerHTML`.
- Solo tocar contenedores `aria-*`. No hacer push sin revisión.
- La documentación debe describir solo lo que existe.

## Reparto sugerido de trabajo entre subagentes (plan Claude Pro)
Para ahorrar cuota, usar un modelo más barato/rápido para lo mecánico y reservar el más capaz para lo que requiere criterio:
- Modelo económico: ediciones mecánicas, traducciones, actualizar documentación, renombrados, añadir una herramienta sencilla siguiendo el patrón de `tools.py`.
- Modelo potente: diseño de funcionalidades, seguridad (auth, CSRF, TLS), depuración de fallos en el bucle de herramientas o en Caddy, revisión final.
- Hacer las pruebas reales (`docker compose`, `curl`) en el hilo principal; los subagentes parten sin contexto, así que darles rutas y objetivo concretos.
