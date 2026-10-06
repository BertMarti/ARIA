# CLAUDE.md

Instrucciones para Claude Code en este repositorio (ARIA).

## Qué es
Asistente local estilo "Jarvis" para Raspberry Pi: FastAPI + Ollama + Caddy en Docker Compose. Sin APIs de pago.

## Estructura
- `docker-compose.yml`: servicios `ollama`, `app`, `caddy` (proyecto `aria`, contenedores `aria-*`).
- `caddy/Caddyfile`: HTTPS con CA interna, certificados bajo demanda autorizados por `/internal/tls-ask`.
- `app/aria/`: `main.py` (rutas, middleware de sesión/CSRF), `origen.py` (regla CSRF Origin/Sec-Fetch-Site/Referer), `auth.py` (sesión, scrypt, versión de sesión), `chat.py` (bucle de herramientas + persistencia), `db.py` (SQLite `data/aria.db`), `tools.py` (herramientas + `_INTENCIONES`), `shield.py` (Pi-hole v6, sid único en caché), `vpn.py` (wg-easy v15, lista blanca de campos), `sistema.py` (/proc y /sys), `modelos.py` (Ollama), `services.py`, `spotify.py`, `config.py`.
- `app/static/`: HTML/CSS/JS sin build (`util.js`, `md.js`, `chat.js`, `control.js`, `inicio.js`, `ajustes.js`, `app.js`), `manifest.webmanifest`, `icon.svg`.
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
- Toda ruta requiere sesión salvo `/login`, `/health`, `/internal/tls-ask` y CSS/JS de login, manifest e icono (lista `PUBLICAS` en `main.py`).
- CSRF: `origen.origen_permitido`. `Origin: null` solo vale con `Sec-Fetch-Site: same-origin` (o Referer del mismo host). Caddy usa `Referrer-Policy strict-origin-when-cross-origin`.
- Las claves privadas de WireGuard nunca van al navegador (solo el `.conf` descargado a petición). `/api/secret/{shield|vpn}` devuelve las contraseñas de los paneles solo a sesiones autenticadas.
- CSP estricta sin estilos/scripts en línea: los anchos de barras se ponen por CSSOM (`el.style.width`), nunca con atributo `style`.
- No editar con `sed -i` archivos montados individualmente en contenedores (cambia el inodo).
- Commits terminan con la línea `Co-Authored-By: ...` que indique el entorno.

## Añadir una herramienta
Ver `SKILLS.md`: se decora una función async con `@tool` en `app/aria/tools.py`, se añaden sus palabras clave a `_INTENCIONES` (si no, el modelo no la recibe) y una prueba en `app/tests/test_tools.py`. Las herramientas destructivas (borrar) no se exponen al modelo.

## No hacer
- No publicar puertos de `ollama` ni `app` en el host.
- No tocar contenedores que no empiecen por `aria-` ni los repos HEIMDALL / SHIELD-DNS.
- Puertos 53, 8080, 8443, 51820/udp y 51843 pertenecen a otros proyectos.
- No hacer `git push` sin revisión.
- No afirmar que ARIA controla Netflix: solo genera enlaces de búsqueda.
