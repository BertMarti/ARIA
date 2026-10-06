# CLAUDE.md

Instrucciones para Claude Code en este repositorio (ARIA).

## Qué es
Asistente local estilo "Jarvis" para Raspberry Pi: FastAPI + Ollama + Caddy en Docker Compose. Sin APIs de pago.

## Estructura
- `docker-compose.yml`: servicios `ollama`, `app`, `caddy` (proyecto `aria`, contenedores `aria-*`).
- `caddy/Caddyfile`: HTTPS con CA interna, certificados bajo demanda autorizados por `/internal/tls-ask`.
- `app/aria/`: `main.py` (rutas, middleware de sesión/CSRF), `auth.py`, `chat.py` (bucle de herramientas), `tools.py` (herramientas), `services.py` (SHIELD-DNS/HEIMDALL), `spotify.py`, `config.py`.
- `app/static/`: HTML/CSS/JS sin paso de build.
- `install.sh` / `uninstall.sh`, `.env.example`, `data/` (ignorado por git).

## Ejecutar y probar
```bash
docker compose config
docker compose up -d --build
docker compose ps                      # los tres deben estar healthy
curl -k https://<IP>/health            # -> ok
docker compose logs -f app
```
Prueba real: login con `ARIA_USER`/`ARIA_PASSWORD` de `.env` (cookie con `curl -c`), luego `POST /api/chat` con `{"messages":[{"role":"user","content":"..."}]}` (respuesta NDJSON).

## Convenciones
- Toda la interfaz, documentación, comentarios y mensajes de commit en español (España).
- Nunca subir secretos: `.env` y `data/` están en `.gitignore`. Nada de credenciales en ejemplos.
- Dependencias mínimas (`app/requirements.txt`); no añadir frameworks de frontend ni paso de build.
- Recursos de la Pi: 8 GB de RAM compartidos con otros servicios; un solo modelo cargado (`OLLAMA_MAX_LOADED_MODELS=1`).
- Salida del modelo siempre como texto en el DOM (nunca `innerHTML` con contenido del modelo).
- Toda ruta requiere sesión salvo `/login`, `/health`, `/internal/tls-ask` y CSS/JS de login (lista `PUBLICAS` en `main.py`).
- Commits terminan con la línea `Co-Authored-By: ...` que indique el entorno.

## Añadir una herramienta
Ver `SKILLS.md`: se decora una función async con `@tool` en `app/aria/tools.py`; no hay que tocar nada más.

## No hacer
- No publicar puertos de `ollama` ni `app` en el host.
- No tocar contenedores que no empiecen por `aria-` ni los repos HEIMDALL / SHIELD-DNS.
- Puertos 53, 8080, 8443, 51820/udp y 51843 pertenecen a otros proyectos.
- No hacer `git push` sin revisión.
- No afirmar que ARIA controla Netflix: solo genera enlaces de búsqueda.
