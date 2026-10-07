# SKILLS.md

## Capacidades reales de ARIA
| Herramienta | Descripción |
|---|---|
| `fecha_hora` | Fecha y hora actuales (zona `ARIA_TZ`) |
| `estado_servicios` | Estado de SHIELD-DNS (DNS + web 8443) y HEIMDALL (puerto 51843) |
| `spotify_play` / `spotify_pause` / `spotify_siguiente` / `spotify_anterior` | Control de reproducción (requiere Premium y dispositivo activo) |
| `spotify_actual` | Canción en reproducción |
| `spotify_buscar_y_reproducir` | Busca una canción y la reproduce |
| `estado_bloqueador` / `pausar_bloqueador(minutos 1-120)` / `reanudar_bloqueador` | Pi-hole (SHIELD-DNS) |
| `dispositivos_vpn` | Lista dispositivos VPN y cuáles están conectados |
| `crear_dispositivo_vpn(nombre)` / `activar_dispositivo_vpn(nombre)` / `desactivar_dispositivo_vpn(nombre)` | Gestión de la VPN por nombre (borrar solo en la interfaz) |
| `estado_sistema` | Temperatura, RAM, disco, carga y uptime de la Pi |
| `buscar_en_internet(consulta)` / `noticias(tema)` | Busca en internet (SearXNG) y devuelve títulos, extractos y enlaces; citar las fuentes. Disponible para ambos roles |
| `buscar_en_netflix` | Devuelve un enlace de búsqueda. ARIA **no** puede controlar Netflix |

Además: Inicio con lanzador de aplicaciones, chat con conversaciones guardadas, Centro de control (SHIELD-DNS, HEIMDALL, Sistema, Spotify) y Ajustes (modelos, voz, contraseña). Las herramientas dependen de que el modelo admita tool calling; si no, ARIA responde sin ellas.

## Playbook: añadir una herramienta
1. En `app/aria/tools.py` añade:
   ```python
   @tool("mi_herramienta", "Qué hace", {"param": ("string", "descripción")}, ("param",))
   async def mi_herramienta(param: str) -> str:
       return "resultado"
   ```
2. Añade una entrada en `_INTENCIONES` (mismo archivo) con las palabras clave que deben activarla.
   **Sin este paso el modelo nunca la verá**: ARIA solo ofrece al modelo las herramientas
   relacionadas con lo que pregunta el usuario, porque un modelo de 3B las usa sin motivo si se le dan todas.
3. Si necesita lógica externa, ponla en un módulo aparte (como `spotify.py`).
4. Reconstruye: `docker compose up -d --build app`.
5. Añade pruebas en `app/tests/test_tools.py` (mensajes de charla no deben activarla) y ejecútalas.
6. Prueba con `POST /api/chat` y comprueba que aparece el evento `herramienta`.
7. Documenta la herramienta en este archivo y en `README.md`.

## Playbook: añadir un proveedor de IA nuevo (cerebro)
1. Si es compatible con OpenAI (`/chat/completions` con streaming SSE y `tools`): añade en `PROVEEDORES` de `app/aria/cerebros.py` un `OpenAICompatible(id, nombre, url, "MI_CLAVE", "ARIA_MODELO_MIO", "modelo-por-defecto")`. Si no, crea una subclase de `Proveedor` con `async def ronda(self, msgs, con_tools=True)` que emita `{"type":"token"|"pensando"|"llamadas"|"aviso"}` y lance `ProveedorError(tipo, mensaje, espera)` (`cuota`, `clave`, `modelo`, `timeout`, `red`, `http`).
2. Añade su id a `ORDEN_DEFECTO`, las variables a `.env.example` y documenta coste y privacidad en el README (sección Cerebros).
3. Comprueba con `curl` el modelo, la latencia y una llamada a herramienta real antes de fijar el modelo por defecto (los modelos se retiran: `gemini-2.5-flash` dio 404).
4. Añade pruebas en `app/tests/test_cerebros.py` (conversión de mensajes, caída ante 429/timeout/clave) y verifica en Ajustes → Cerebros con «Probar».
5. Nunca registres ni muestres la clave.

## Playbook: cambiar de modelo
1. (Cerebro local) Ajustes → Modelos: «Descargar» y «Usar» (se guarda en `data/model.txt`).
2. Alternativa: `ARIA_MODEL` en `.env` (el archivo de `data/` tiene prioridad).

## Playbook: configurar Spotify
1. Crea una app en <https://developer.spotify.com/dashboard>.
2. Añade la Redirect URI `https://<IP>/spotify/callback` (igual que `SPOTIFY_REDIRECT_URI`).
3. Rellena `SPOTIFY_CLIENT_ID` y `SPOTIFY_CLIENT_SECRET` en `.env`; `docker compose up -d`.
4. En Ajustes → Spotify, pulsa "Conectar Spotify". El token queda en `data/spotify_token.json`.

## Playbook: invitar a alguien
1. Ajustes → Usuarios → «Invitar usuario»: email, nombre y rol (`usuario` salvo que deba administrar).
2. Para que entre desde fuera, añade su email en Cloudflare Access: Zero Trust → Access → Applications → ARIA → Policies (ARIA no lo hace por ti).
3. Para entrar desde casa, pulsa «Poner contraseña para casa» y dásela (mínimo 10 caracteres); entra con su email o usuario.
4. Para quitarle el acceso: «Desactivar» (cierra sus sesiones al instante) o «Eliminar» (borra también sus conversaciones) y retira su email de la política de Access.
Los emails de `ARIA_ADMIN_EMAILS` en `.env` son siempre administradores y no se pueden eliminar.

## Playbook: ver y borrar lo que ARIA recuerda
- **Tú mismo**: Ajustes → Memoria. Lista de recuerdos (editar/borrar), añadir uno, diario de 14 días (borrar por día), interruptor «Aprender automáticamente» y «Borrar toda mi memoria».
- **Por chat**: «recuerda que…», «olvida que…» (herramientas `recordar` / `olvidar`).
- **Por API** (sesión iniciada): `GET /api/memoria`, `DELETE /api/memoria/{id}`, `DELETE /api/memoria` (todo), `DELETE /api/diario/AAAA-MM-DD`, `POST /api/memoria/ajustes {"aprender": false}`.
- **Administrador**: `POST /api/diario/generar` (cuerpo opcional `{"fecha":"AAAA-MM-DD","todos":true}`) lanza el diario a mano. Tablas en `data/aria.db`: `recuerdos`, `diario`, `memoria_ajustes`, `resumen_dia`; copia previa a la memoria en `data/aria.db.bak-memoria`.
- Para que ARIA deje de enviar tu memoria a la nube, borra tus recuerdos y desactiva el aprendizaje.

## Playbook: actualizar
`./update.sh`.

## Playbook: copia de seguridad
`./backup.sh` (`.env` + `data/` en `backups/`, 7 copias). Restaurar: ver README.

## Playbook: conectar SHIELD-DNS / HEIMDALL
Rellena `SHIELD_PASSWORD`, `VPN_USER`, `VPN_PASSWORD` en `.env` (o deja que `install.sh` los tome de `../SHIELD-DNS/.env` y `../HEIMDALL/.env`) y `docker compose up -d`.
