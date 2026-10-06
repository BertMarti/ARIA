# MEMORY.md

## Decisiones
- **Ollama local**: sin coste ni nube. Modelo por defecto `llama3.2:3b` (cabe en 8 GB y soporta herramientas).
- **FastAPI sin build de frontend**: HTML/CSS/JS plano, mínimas dependencias (fastapi, uvicorn, httpx, itsdangerous, tzdata).
- **Caddy con `tls internal` + `on_demand`**: los navegadores no envían SNI al entrar por IP; se usa `default_sni` con la IP LAN y un endpoint `ask` (`/internal/tls-ask`) que solo autoriza los hosts de `ARIA_HOSTS`. Verificado con `curl -k` por IP y por `.local`; un host no listado es rechazado.
- **Sesión**: cookie firmada (itsdangerous), HttpOnly, Secure, SameSite=Lax; comparación en tiempo constante; 5 fallos/5 min por IP bloquean (en memoria). CSRF: comprobación de `Origin` en POST.
- **DNS check con UDP crudo** (sin dnspython) para no añadir dependencias.
- **Spotify Authorization Code** con token en `data/` (permisos 0600). Netflix: solo enlaces de búsqueda (no hay API).
- `ollama` y `app` no se publican; solo Caddy expone 80/443.

## Mapa de puertos
| Proyecto | Puertos |
|---|---|
| ARIA | 80, 443 |
| SHIELD-DNS | 53, 8080, 8443 |
| HEIMDALL | 51820/udp, 51843 |

## Limitaciones conocidas
- Spotify requiere Premium y un dispositivo activo; el flujo OAuth completo no se ha podido probar sin credenciales reales (sí la ruta "no configurado").
- El modelo 3B es irregular con herramientas: en una prueba, ante un saludo, respondió con un JSON de herramienta inventado como texto en vez de contestar; con peticiones claras (hora, estado de servicios, Netflix) el bucle funcionó.
- `mem_limit` se ignora en esta Pi (kernel sin cgroup de memoria).
- Latencia: la primera respuesta tras cargar el modelo tardó ~57 s.
- Limitador de login y estado de conversación solo en memoria.
- RAM observada (Pi de 8 GB con escritorio y otros contenedores): con el modelo cargado, ~5,8 GiB usados y ~2,1 GiB disponibles (antes de cargar: ~3,5 GiB usados).

## Registro de cambios
- **2026-10-06**: reescritura completa. Docker Compose (ollama, app, caddy), login, chat con streaming y bucle de herramientas, panel de servicios, Spotify, instalador/desinstalador, documentación en español.
