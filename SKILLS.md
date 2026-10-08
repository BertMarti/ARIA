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
| `ubicaciones_vpn(dispositivo?)` | Consulta las últimas ubicaciones conocidas de la VPN (solo administradores) |
| `crear_dispositivo_vpn(nombre, caduca?)` / `activar_dispositivo_vpn(nombre)` / `desactivar_dispositivo_vpn(nombre)` | Gestión de la VPN por nombre (borrar solo en la interfaz); la caducidad admite 24h, 7d, fecha o lenguaje natural |
| `estado_sistema` | Temperatura, RAM, disco, carga y uptime de la Pi |
| `buscar_en_internet(consulta)` / `noticias(tema)` | Busca en internet (SearXNG) y devuelve títulos, extractos y enlaces; citar las fuentes. Disponible para ambos roles |
| `buscar_en_netflix` | Devuelve un enlace de búsqueda. ARIA **no** puede controlar Netflix |
| `registrar_movimiento`, `resumen_mes`, `gastos_por_categoria`, `comparar_meses`, `presupuesto`, `estado_presupuestos`, `buscar_movimientos` | Agente Finanzas (datos del usuario) |
| `estado_red`, `dispositivos_red`, `dispositivos_nuevos`, `marcar_dispositivo_conocido`, `medir_latencia`, `test_velocidad` | Agente Redes |
| `informe_seguridad`, `escanear_red`, `estado_escaneo`, `bloqueos_por_cliente` | Agente Seguridad (solo admin) |
| `recordatorio(texto, cuando, repetir)` / `mis_recordatorios` / `borrar_recordatorio` | Recordatorios del usuario (todos los roles); `cuando` en ISO local o frase («mañana a las 9») |

Además: avisos (campana, Telegram y notificaciones push), Inicio con lanzador de aplicaciones, chat con conversaciones guardadas, Centro de control (SHIELD-DNS, HEIMDALL, Sistema, Spotify) y Ajustes (modelos, voz, contraseña). Voz: micrófono (pulsar para hablar), «Leer» con Piper y «manos libres» diciendo «Aria». Las herramientas dependen de que el modelo admita tool calling; si no, ARIA responde sin ellas.

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

## Playbook: añadir un agente
1. En `app/aria/agentes.py` añade un `Agente(id, nombre, icono, descripción, prompt, herramientas, roles, cerebro, palabras)` a `AGENTES`. `roles=frozenset({"admin"})` si es solo de administrador; `palabras` son las regex del enrutado automático.
2. Sus herramientas van en `tools.py` con `especialista=True` (y `usa_uid=True` si son datos del usuario) y entrada en `_INTENCIONES`. Si un `usuario` debe usarlas, añádelas a `tools.DE_USUARIO`.
3. Endpoints nuevos: en un `APIRouter` y, si un `usuario` debe llegar, en `permisos.py` y en `RUTAS_USUARIO_AGENTES` de `test_permisos.py`.
4. Interfaz: color de la insignia en `style.css` (`.agente-badge.ag-<id>`) y nombres de herramientas en `chat.js`.
5. Pruebas en `test_agentes.py` (enrutado, roles) y documenta en README y aquí.

## Playbook: importar el extracto del banco
Finanzas → Importar extracto CSV → revisar el mapeo de columnas y la vista previa → Importar. Si un banco no se detecta, añade sus nombres de columna a `_CLAVES` de `finanzas_csv.py` y un caso a `test_finanzas.py`.

## Playbook: revisar la seguridad de la red
1. Seguridad → «Escanear ahora» (100 puertos) o completo (1000); tarda 3-10 minutos. O en el chat: «@seguridad lanza un escaneo» y luego «@seguridad dame el informe».
2. Corrige primero lo de gravedad alta (Telnet, VNC, RDP, firmware con CVE altos), después las medias (UPnP, paneles sin HTTPS, dispositivos sin reconocer).
3. En Red marca como conocidos tus dispositivos (con alias) para que solo resalten los nuevos.
4. El escaneo semanal (domingo 04:00) avisa de puertos nuevos respecto al anterior.
Nunca cambies `ARIA_RED_PERMITIDA` a una red que no sea tuya.

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

## Playbook: voz
- Usar: botón del micrófono (mantener y soltar), «Leer» en cada respuesta, «Manos libres» en el chat → di «Aria, …». Ajustes → Voz para micrófono, lectura automática y velocidad.
- Transcripción: `GROQ_API_KEY` en `.env` (Groq Whisper). Sin clave o si falla, transcribe `aria-voz` en local.
- Comprobar: Ajustes → Voz muestra «Transcripción: Groq (local de respaldo) · Voz de ARIA: Piper…». Logs: `docker compose logs voz`.
- Cambiar la voz de Piper o el modelo Whisper: `docker compose build --build-arg VOZ_PIPER=es_ES-davefx-medium --build-arg VOZ_WHISPER=small voz` (small es ~2,5 veces más lento en la Pi).
- Si «Aria» se activa sola: sube `VOZ_CONFIANZA` en `.env` (por defecto 0.6) y `docker compose up -d`.

## Playbook: crear el bot de Telegram y vincularlo
1. Telegram → @BotFather → `/newbot` → nombre «ARIA» y usuario acabado en `bot`. Copia el token (no lo pegues en ningún chat).
2. `.env`: `TELEGRAM_BOT_TOKEN=<token>`; `docker compose up -d` (recrea `aria-app`).
3. `docker compose exec app python -m aria.telegram --probar` → «Token válido. Bot: @…». Si dice 401, el token está mal copiado.
4. ARIA → Ajustes → Avisos → «Vincular Telegram» → abrir el enlace `t.me/<bot>?start=<código>` → Iniciar. Debe contestar «Este chat queda vinculado…». Prueba `/estado` y «Probar avisos».
5. Para quitarlo: «Desvincular» en Ajustes o `/desvincular` en el chat. Si alguien desconocido escribe al bot, solo recibe «No te conozco…».

## Playbook: activar las notificaciones en el móvil
1. Abre **https://aria.tu-dominio.com** (no la IP: hace falta certificado válido). En iPhone (iOS 16.4+): Compartir → Añadir a pantalla de inicio y abre ARIA desde ese icono.
2. Ajustes → Avisos → «Activar notificaciones en este dispositivo» → Permitir.
3. «Enviar notificación de prueba». Si no llega: revisa que el navegador/sistema no tenga las notificaciones de ARIA bloqueadas y que el dispositivo esté en la lista.
4. Si se regeneran las claves VAPID, hay que volver a activarlas en cada dispositivo.

## Playbook: avisos y recordatorios
- «Recuérdame mañana a las 9 llamar al taller», «avísame en 20 minutos», «todos los lunes a las 8…»; lista: «¿qué recordatorios tengo?»; borrar: «borra el recordatorio 3» (o en Ajustes → Recordatorios).
- Ajustes → Avisos: tipos, horas de silencio, resumen de buenos días (hora y canal), «Probar avisos». La campana de la cabecera muestra los no leídos.

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
