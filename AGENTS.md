# AGENTS.md

Guía para cualquier agente de programación (convención agents.md).

## Proyecto
ARIA: asistente local en Raspberry Pi (FastAPI + Ollama + Caddy, Docker Compose). Código en `app/aria/`, frontend sin build en `app/static/`, proxy en `caddy/Caddyfile`.

## Comandos
- Validar: `docker compose config`
- Levantar: `docker compose up -d --build` y `docker compose ps` (tres contenedores healthy)
- Comprobar: `curl -k https://<IP>/health`
- Logs: `docker compose logs -f app`

## Reglas
- Español (España) en UI, documentación, comentarios y commits.
- Sin secretos en el repo (`.env`, `data/` ignorados).
- Dependencias mínimas; sin build de frontend; salida del modelo solo como texto escapado.
- Respetar los puertos de otros proyectos: ARIA 80/443; SHIELD-DNS 53, 8080, 8443; HEIMDALL 51820/udp, 51843.
- Solo tocar contenedores `aria-*`. No hacer push sin revisión.
- La documentación debe describir solo lo que existe.

## Reparto sugerido de trabajo entre subagentes (plan Claude Pro)
Para ahorrar cuota, usar un modelo más barato/rápido para lo mecánico y reservar el más capaz para lo que requiere criterio:
- Modelo económico: ediciones mecánicas, traducciones, actualizar documentación, renombrados, añadir una herramienta sencilla siguiendo el patrón de `tools.py`.
- Modelo potente: diseño de funcionalidades, seguridad (auth, CSRF, TLS), depuración de fallos en el bucle de herramientas o en Caddy, revisión final.
- Hacer las pruebas reales (`docker compose`, `curl`) en el hilo principal; los subagentes parten sin contexto, así que darles rutas y objetivo concretos.
