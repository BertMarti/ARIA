# SKILLS.md

## Capacidades reales de ARIA
| Herramienta | Descripción |
|---|---|
| `fecha_hora` | Fecha y hora actuales (zona `ARIA_TZ`) |
| `estado_servicios` | Estado de SHIELD-DNS (DNS + web 8443) y HEIMDALL (puerto 51843) |
| `spotify_play` / `spotify_pause` / `spotify_siguiente` / `spotify_anterior` | Control de reproducción (requiere Premium y dispositivo activo) |
| `spotify_actual` | Canción en reproducción |
| `spotify_buscar_y_reproducir` | Busca una canción y la reproduce |
| `buscar_en_netflix` | Devuelve un enlace de búsqueda. ARIA **no** puede controlar Netflix |

Además: chat en streaming, gestión del modelo (descarga del modelo configurado) y panel de servicios. Las herramientas dependen de que el modelo admita tool calling; si no, ARIA responde sin ellas.

## Playbook: añadir una herramienta
1. En `app/aria/tools.py` añade:
   ```python
   @tool("mi_herramienta", "Qué hace", {"param": ("string", "descripción")}, ("param",))
   async def mi_herramienta(param: str) -> str:
       return "resultado"
   ```
2. Si necesita lógica externa, ponla en un módulo aparte (como `spotify.py`).
3. Reconstruye: `docker compose up -d --build app`.
4. Prueba con `POST /api/chat` y comprueba que aparece el evento `herramienta`.
5. Documenta la herramienta en este archivo y en `README.md`.

## Playbook: cambiar de modelo
1. Edita `ARIA_MODEL` en `.env`.
2. `docker compose exec ollama ollama pull <modelo>` (o botón del panel tras reiniciar).
3. `docker compose up -d` para recrear `aria-app`.

## Playbook: configurar Spotify
1. Crea una app en <https://developer.spotify.com/dashboard>.
2. Añade la Redirect URI `https://<IP>/spotify/callback` (igual que `SPOTIFY_REDIRECT_URI`).
3. Rellena `SPOTIFY_CLIENT_ID` y `SPOTIFY_CLIENT_SECRET` en `.env`; `docker compose up -d`.
4. En el panel, pulsa "Conectar Spotify". El token queda en `data/spotify_token.json`.

## Playbook: actualizar
`git pull && ./install.sh`. Para imágenes base: `docker compose pull ollama caddy && docker compose up -d --build`.
