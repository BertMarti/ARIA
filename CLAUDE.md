# CLAUDE.md

Instrucciones para Claude Code en este repositorio (ARIA).

## Qué es
Asistente doméstico local para Raspberry Pi: FastAPI + Ollama + Caddy en Docker Compose. Sin APIs de pago.

## Estructura
- `docker-compose.yml`: servicios `ollama`, `searxng`, `app`, `caddy` (proyecto `aria`, contenedores `aria-*`).
- `caddy/Caddyfile`: HTTPS con CA interna, certificados bajo demanda autorizados por `/internal/tls-ask`.
- `app/aria/`: `main.py` (rutas, middleware de sesión/CSRF), `origen.py` (regla CSRF Origin/Sec-Fetch-Site/Referer), `auth.py` (cookie firmada con id de usuario + versión, scrypt, limitador), `usuarios.py` (tabla `usuarios`, roles, migración del admin único), `permisos.py` (lista blanca del rol `usuario`; denegar por defecto), `sso.py` (verificación del JWT de Cloudflare Access con PyJWT), `cerebros.py` (cadena de proveedores: Ollama nativo local/nube + OpenAI-compatible Groq/Gemini, esperas por cuota, `data/cerebros.json`), `chat.py` (bucle de herramientas + relevo entre cerebros + persistencia), `db.py` (SQLite `data/aria.db`), `busqueda.py` (cliente de SearXNG: caché 10 min, dedupe por dominio, texto ≤1500), `tools.py` (herramientas + `_INTENCIONES`), `shield.py` (Pi-hole v6, sid único en caché), `vpn.py` (wg-easy v15, lista blanca de campos), `sistema.py` (/proc y /sys), `modelos.py` (Ollama), `services.py`, `spotify.py`, `config.py`.
- `app/static/`: HTML/CSS/JS sin build (`util.js`, `md.js`, `chat.js`, `control.js`, `inicio.js`, `ajustes.js`, `usuarios.js`, `app.js`), `manifest.webmanifest`, `icon.svg`.
- `app/tests/`: pytest (`python -m pytest`) y `md.test.js` (node).
- `install.sh` / `update.sh` / `backup.sh` / `uninstall.sh`, `.env.example`, `data/` y `backups/` (ignorados por git).

## Ejecutar y probar
```bash
docker compose config
docker compose up -d --build
docker compose ps                      # los tres deben estar healthy
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

## Memoria y resumen de buenos días
- `memoria.py` (recuerdos, diario, ajustes, contexto del prompt; TODO se filtra por `user_id`), `aprender.py` (extracción en segundo plano, solo nube), `diario.py` (resumen diario + planificador 03:30 + recuperación), `briefing.py` (resumen de hoy, caché en `resumen_dia`, versión hablada), `tiempo.py` (fechas locales, límites de día con DST).
- La identidad de las herramientas de memoria sale de `memoria.uid_actual` (la fija `chat.conversar`), nunca de los argumentos del modelo. `recordar`/`olvidar` las tiene todo rol.
- Presupuesto del prompt: nube ≤ ~1 200 (recuerdos) + ~900 (diario); local ≤ 300 y sin diario. No ampliarlo sin medir (el local lee ~11 tokens/s).
- Nunca guardar secretos (`memoria.parece_secreto`). Los datos solo de admin del resumen (`vpn`, `copia`) se quitan en el servidor (`briefing.para_rol`).
- Las tablas están en `db.iniciar`; haz copia de `data/aria.db` antes de cambiar el esquema.

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
