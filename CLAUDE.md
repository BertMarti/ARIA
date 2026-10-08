# CLAUDE.md

Instrucciones para Claude Code en este repositorio (ARIA).

## Qué es
Asistente doméstico local para Raspberry Pi: FastAPI + Ollama + Caddy en Docker Compose. Sin APIs de pago.

## Estructura
- `docker-compose.yml`: servicios `ollama`, `searxng`, `app`, `voz`, `escaner`, `caddy` (proyecto `aria`, contenedores `aria-*`). `voz` solo está en la red interna `voz` (sin Internet ni puertos).
- `caddy/Caddyfile`: HTTPS con CA interna, certificados bajo demanda autorizados por `/internal/tls-ask`.
- `app/aria/`: `main.py` (rutas, middleware de sesión/CSRF), `origen.py` (regla CSRF Origin/Sec-Fetch-Site/Referer), `auth.py` (cookie firmada con id de usuario + versión, scrypt, limitador), `usuarios.py` (tabla `usuarios`, roles, migración del admin único), `permisos.py` (lista blanca del rol `usuario`; denegar por defecto), `sso.py` (verificación del JWT de Cloudflare Access con PyJWT), `cerebros.py` (cadena de proveedores: Ollama nativo local/nube + OpenAI-compatible Groq/Gemini, esperas por cuota, `data/cerebros.json`), `chat.py` (bucle de herramientas + relevo entre cerebros + persistencia), `db.py` (SQLite `data/aria.db`), `busqueda.py` (cliente de SearXNG: caché 10 min, dedupe por dominio, texto ≤1500), `tools.py` (herramientas + `_INTENCIONES`), `shield.py` (Pi-hole v6, sid único en caché), `vpn.py` (wg-easy v15, lista blanca de campos), `sistema.py` (/proc y /sys), `voz.py` (validación de audio, Groq Whisper → aria-voz, limitador por usuario, limpieza de texto para TTS, puente WebSocket), `modelos.py` (Ollama), `services.py`, `spotify.py`, `config.py`.
- `voz/`: contenedor `aria-voz` (`servidor.py`: faster-whisper base int8, Piper `es_ES-sharvard-medium` con la voz femenina «F» (`VOZ_HABLANTE`), Vosk `vosk-model-small-es` con gramática cerrada para «Aria»; modelos descargados en la imagen por `descargar.py`).
- `app/static/`: HTML/CSS/JS sin build (`util.js`, `md.js`, `voz.js` (micrófono, TTS, manos libres), `pcm-worklet.js` (AudioWorklet a PCM 16 kHz), `chat.js`, `control.js`, `inicio.js`, `ajustes.js`, `usuarios.js`, `app.js`), `manifest.webmanifest`, `icon.svg`.
- `app/tests/`: pytest (`python -m pytest`) y `md.test.js` (node).
- `install.sh` / `update.sh` / `backup.sh` / `uninstall.sh`, `.env.example`, `data/` y `backups/` (ignorados por git).

## Ejecutar y probar
```bash
docker compose config
docker compose up -d --build
docker compose ps                      # los cuatro deben estar healthy
curl -k https://<IP>/health            # -> ok
docker compose logs -f app
```
Pruebas unitarias: ver README (sección Pruebas). Prueba real: login con `ARIA_USER`/`ARIA_PASSWORD` de `.env` (cookie con `curl -c`), luego `POST /api/chat` con `{"conversation_id":null,"message":"..."}` (respuesta NDJSON; el primer evento es `conv`). Los POST necesitan cabecera `Origin` igual al host (como un navegador).

## Convenciones
- Toda la interfaz, documentación, comentarios y mensajes de commit en español (España).
- Nunca subir secretos: `.env` y `data/` están en `.gitignore`. Nada de credenciales en ejemplos.
- Dependencias mínimas (`app/requirements.txt`); no añadir frameworks de frontend ni paso de build.
- Recursos de la Pi: 8 GB de RAM compartidos con otros servicios; un solo modelo cargado (`OLLAMA_MAX_LOADED_MODELS=1`).
- Salida del modelo siempre como texto en el DOM (nunca `innerHTML` con contenido del modelo).
- Toda ruta requiere sesión salvo `/login`, `/health`, `/internal/tls-ask` y CSS/JS de login, manifest e icono (lista `PUBLICAS` en `main.py`). Tras la sesión, `permisos.permitido(rol, método, ruta)` decide: `admin` todo; `usuario` solo la lista blanca de `permisos.py`. **Un endpoint nuevo es solo para admin salvo que se añada ahí** (hay una prueba que recorre todas las rutas).
- SSO: nunca confiar en `Cf-Access-Authenticated-User-Email`; solo vale el JWT verificado (`sso.identificar`). Sin red a Cloudflare es fallo transitorio (página «Entrando…» que reintenta), con JWT inválido se cae al formulario. Las pruebas usan una clave RSA local y `sso._descargar_jwks` simulado.
- Conversaciones: toda función de `db.py` recibe `uid` y filtra por `user_id` (prueba IDOR en `test_permisos.py`). Herramientas del chat por rol: `tools.permitidas(rol)`; `ejecutar` rechaza las no permitidas.
- CSRF: `origen.origen_permitido`. `Origin: null` solo vale con `Sec-Fetch-Site: same-origin` (o Referer del mismo host). Caddy usa `Referrer-Policy strict-origin-when-cross-origin`.
- Las claves privadas de WireGuard nunca van al navegador (solo el `.conf` descargado a petición). `/api/secret/{shield|vpn}` devuelve las contraseñas de los paneles solo a sesiones autenticadas.
- CSP estricta sin estilos/scripts en línea: los anchos de barras se ponen por CSSOM (`el.style.width`), nunca con atributo `style`.
- No editar con `sed -i` archivos montados individualmente en contenedores (cambia el inodo).
- Commits terminan con la línea `Co-Authored-By: ...` que indique el entorno.

## Voz
- Endpoints `GET /api/voz/estado`, `POST /api/voz/transcribir` (audio crudo; `Content-Type` audio/*), `POST /api/voz/hablar` y WebSocket `/api/voz/despertar`, para ambos roles (lista blanca de `permisos.py`).
- **El middleware HTTP no se aplica a los WebSocket**: `ws_despertar` comprueba Origin (obligatorio e igual al Host), cookie de sesión y rol. Cualquier WebSocket nuevo debe hacer lo mismo.
- El audio nunca se escribe en disco ni en SQLite. No añadir logs con audio ni texto transcrito.
- La palabra de activación es «Aria» (nunca otra). Ajustar señuelos/umbral en `voz/servidor.py` y volver a medir con frases de Piper (ver MEMORY.md).
- CSP: el audio se reproduce con WebAudio (`decodeAudioData`), así que no hace falta `media-src blob:`; el WebSocket va a `'self'`.
- `faster-whisper` 1.2.1 no funciona con PyAV 19 (`metadata_errors`): `av<19`. `libvosk.so` necesita `libatomic1`.

## Visión (2026-10-08)
- `vision.py`: tipo real por bytes (JPEG/PNG/WebP), ≤ 5 MB, `sin_metadatos` (quita APP1/APP13/COM de JPEG, tEXt/eXIf de PNG, EXIF/XMP de WebP; conserva ICC) sin Pillow; proveedores OpenAI-compatibles Gemini → Groq con esperas en `cerebros._esperas` (claves `vision_*`); nunca el local. Límite por usuario con `voz.Limitador`.
- `/api/chat` acepta `imagen` (data URL; cuerpo ≤ 7,2 MB) → `chat.conversar_imagen` (sin herramientas ni agentes, sin aprendizaje). Evento `ticket` con ficha en memoria (`vision.proponer`/`tomar`: usuario, un uso, 30 min) → `POST`/`DELETE /api/vision/tickets/{token}`. Telegram usa sus fichas (`ticket` + `cancelar`).
- CSP sin cambios: las miniaturas son `data:` (ya permitido en `img-src`). Caddy no cambia.

## Memoria y resumen de buenos días
- `memoria.py` (recuerdos, diario, ajustes, contexto del prompt; TODO se filtra por `user_id`), `aprender.py` (extracción en segundo plano, solo nube), `diario.py` (resumen diario + planificador 03:30 + recuperación), `briefing.py` (resumen de hoy, caché en `resumen_dia`, versión hablada), `tiempo.py` (fechas locales, límites de día con DST).
- La identidad de las herramientas de memoria sale de `memoria.uid_actual` (la fija `chat.conversar`), nunca de los argumentos del modelo. `recordar`/`olvidar` las tiene todo rol.
- Presupuesto del prompt: nube ≤ ~1 200 (recuerdos) + ~900 (diario); local ≤ 300 y sin diario. No ampliarlo sin medir (el local lee ~11 tokens/s).
- Nunca guardar secretos (`memoria.parece_secreto`). Los datos solo de admin del resumen (`vpn`, `copia`) se quitan en el servidor (`briefing.para_rol`).
- Las tablas están en `db.iniciar`; haz copia de `data/aria.db` antes de cambiar el esquema.

## Agentes (2026-10-07)
- `agentes.py`: `AGENTES` (aria, finanzas, redes, seguridad) con prompt, herramientas, roles y cerebro preferido. Elección en `chat.elegir_agente`: prefijo `@id` → agente de la conversación (`conversaciones.agente`) → `agentes.enrutar` (palabras clave; empate → `clasificar_con_nube`). Siempre se comprueba `agentes.permitido(id, rol)`; `seguridad` es solo admin.
- Herramientas ofrecidas = `agente.herramientas ∩ tools.permitidas(rol)`; `tools.ejecutar(..., uid=, solo=)` vuelve a comprobarlo. Las de especialista llevan `especialista=True` (ARIA general no las ofrece) y las de datos por usuario `usa_uid=True` (el `uid` lo pone el servidor; el del modelo se descarta).
- Finanzas: `finanzas.py` (tablas `fin_*`, céntimos, siempre `uid`), `finanzas_csv.py` (parser), `api_finanzas.py`. Prueba IDOR en `test_finanzas.py`.
- Redes/Seguridad: `red.py`, `seguridad.py`, `cve.py` (OSV/NVD con caché `seg_cve_cache`), `escaneo.py` (volumen `/escaner`), `escaneo_comun.py` (guardia de CIDR y parser de nmap, compartido con `app/escaner/escaner.py`), `api_red.py`.
- **Nunca** ampliar `ARIA_RED_PERMITIDA` fuera de la LAN ni añadir argumentos de nmap que vengan del usuario/modelo; nada de NSE, fuerza bruta ni exploits. `aria-escaner` es el único contenedor con `network_mode: host`.
- Probar en paralelo sin tocar los contenedores en vivo: proyecto `-p aria-agentes` con contenedores `agt-*` y volúmenes propios.

## Avisos, Telegram y push (2026-10-08)
- `avisos.py`: motor genérico (tablas `avisos`, `avisos_estado`, `avisos_ajustes`; `Chequeo`/`Problema`; `emitir`, `procesar`, `tick`, `bucle`, `Limitador`). Los chequeos están en `avisos_chequeos.py` (devuelven lista de `Problema` o None si no se puede saber). Canales registrados en el arranque (`registrar_canal`): `push.canal` y `telegram.canal`. Un aviso con `TIPOS[tipo][1]` (solo admin) nunca se entrega a un `usuario`.
- `recordatorios.py`: tabla `recordatorios`, `interpretar()` (español → fecha local), `siguiente()` (repeticiones a la misma hora local, DST incluido), `disparar_vencidos()` lo llama el planificador. Herramientas `recordatorio`/`mis_recordatorios`/`borrar_recordatorio` con `usa_uid=True` para todos los roles.
- `telegram.py`: long polling (sin webhook). Solo chats privados vinculados; `callback_data` = fichas aleatorias en `telegram_acciones` (chat + usuario + caducidad, un uso) y las operaciones de `OPS_ADMIN` vuelven a comprobar el rol al confirmar. Nunca registrar URL de la Bot API (llevan el token). Pruebas con `FalsoBot` en `test_telegram.py`.
- `voz_puente.py`: `transcribir(bytes, mime)` y `sintetizar(texto) -> (bytes, mime)` sobre `voz.py`; `aria-voz` devuelve OGG/Opus si se pide `formato: "ogg"` (notas de voz de Telegram).
- `push.py`: Web Push propio (aes128gcm + VAPID ES256 con `cryptography`/PyJWT). Solo endpoints de servicios push conocidos (`HOSTS_PUSH`, anti-SSRF); 404/410 borran la suscripción. `/sw.js` (en `LIBRES`) se sirve con `Service-Worker-Allowed: /` y la versión de los estáticos; no cachea nada. La CSP incluye `worker-src 'self'`.
- API en `api_avisos.py`, abierta a los dos roles en `permisos.py` (todo filtra por el usuario de la sesión). Frontend: `static/avisos.js` (campana + Ajustes → Avisos + Recordatorios); clases CSS `av-item*` (no `.aviso`, que es del chat).

## Añadir una herramienta
Ver `SKILLS.md`: se decora una función async con `@tool` en `app/aria/tools.py`, se añaden sus palabras clave a `_INTENCIONES` (si no, el modelo no la recibe) y una prueba en `app/tests/test_tools.py`. Las herramientas destructivas (borrar) no se exponen al modelo.

## Búsqueda en internet
`aria-searxng` (config en `searxng/settings.yml`, sin puertos publicados, `SEARXNG_SECRET` en `.env`). Herramientas `buscar_en_internet` y `noticias` (en `SOLO_LECTURA`, así que también para `usuario`). Los resultados al modelo van en ≤1500 caracteres con cada URL en su línea; el chat las convierte en enlaces con el DOM (nunca `innerHTML`). Pruebas con SearXNG falso en `app/tests/test_busqueda.py`. Si añades palabras clave de búsqueda, comprueba que la charla normal («hola», «explícame qué es un DNS») no activa nada.

## Cerebros
- `chat.responder` recorre `cerebros.cadena()` en cada ronda; un `ProveedorError` salta al siguiente (aviso + evento `reinicio` si ya había tokens). Los mensajes internos están en formato Ollama; `a_openai()` los convierte y `AcumuladorLlamadas` junta los fragmentos de `tool_calls`.
- `tools.relevantes()` / `rescatar_llamada()` solo se aplican al proveedor `local`; las nubes reciben todas las herramientas.
- Nunca imprimir ni guardar claves (`GROQ_API_KEY`, `GEMINI_API_KEY`); la API solo expone si hay clave. Gemini 3 exige devolver `extra_content.thought_signature` en las llamadas.
- Añadir un proveedor: ver `SKILLS.md`.

## No hacer
- No publicar puertos de `ollama` ni `app` en el host.
- No tocar contenedores que no empiecen por `aria-` ni los repos HEIMDALL / SHIELD-DNS.
- Puertos 53, 8080, 8443, 51820/udp y 51843 pertenecen a otros proyectos.
- No hacer `git push` sin revisión.
- No afirmar que ARIA controla Netflix: solo genera enlaces de búsqueda.
