# MEMORY.md

## Decisiones
- **Ollama local**: sin coste ni nube. Modelo por defecto `llama3.2:3b` (cabe en 8 GB y soporta herramientas).
- **FastAPI sin build de frontend**: HTML/CSS/JS plano, mínimas dependencias (fastapi, uvicorn, httpx, itsdangerous, tzdata).
- **Caddy con `tls internal` + `on_demand`**: los navegadores no envían SNI al entrar por IP; se usa `default_sni` con la IP LAN y un endpoint `ask` (`/internal/tls-ask`) que solo autoriza los hosts de `ARIA_HOSTS`. Verificado con `curl -k` por IP y por `.local`; un host no listado es rechazado.
- **Sesión**: cookie firmada (itsdangerous), HttpOnly, Secure, SameSite=Lax; comparación en tiempo constante; 5 fallos/5 min por IP bloquean (en memoria). CSRF: comprobación de `Origin` en POST.
- **DNS check con UDP crudo** (sin dnspython) para no añadir dependencias.
- **Spotify Authorization Code** con token en `data/` (permisos 0600). Netflix: solo enlaces de búsqueda (no hay API).
- `ollama` y `app` no se publican; solo Caddy expone 80/443.

## Decisiones de voz (2026-10-07)
- **Arquitectura**: la app hace de puerta (sesión, rol, Origin, límites) y un contenedor nuevo `aria-voz` (Python 3.12) hace el trabajo pesado. `aria-voz` no publica puertos y vive solo en la red interna `voz` (`internal: true`, sin Internet): ni Caddy ni Ollama llegan a él. Los modelos se descargan al construir la imagen.
- **Transcripción**: Groq `whisper-large-v3-turbo` (gratis, misma `GROQ_API_KEY`) y relevo automático a `aria-voz` si falla (429 → espera `Retry-After` o 60 s; clave/modelo → 30 min; red → 30 s). El audio sube crudo (sin multipart, sin dependencia nueva), se valida tipo y firma (WebM/Ogg/WAV/MP4/MP3), máx. 1 MB (el navegador corta a 30 s y graba Opus a 32 kbit/s), 12/min y 200/h por usuario. Nunca se escribe en disco.
- **Whisper local `base` int8** y no `small`: medido en la Pi con 4 hilos sobre frases de ~4,5 s, base tardó 2,3-3,5 s (RSS ~235 MB) y small 6-9 s (RSS ~580 MB) con una mejora de calidad pequeña. Es solo el respaldo y la RAM es justa con el LLM cargado. Se carga bajo demanda y se libera tras 10 min sin uso. `small` se puede elegir con `--build-arg VOZ_WHISPER=small`.
- **Voz de ARIA: Piper `es_ES-sharvard-medium`**. Se compararon davefx-medium y sharvard-medium generando las mismas frases y transcribiéndolas con Groq: sharvard 4/4 correctas («Aria, ¿qué hora es?», «Oye, Aria, pon música.»...), davefx 1-2/4 («Adia, ¿qué hora es?», «Gracias.» para «Aria.»). Síntesis ~0,25-0,3 × tiempo real (1,9 s de audio en ~0,5-0,6 s; 3,3 s la primera vez por la carga). Se devuelve WAV y el navegador lo reproduce con WebAudio (`decodeAudioData`), así no hay que añadir `media-src blob:` a la CSP; el texto se trocea por frases para que empiece a sonar enseguida.
- **Palabra de activación «Aria» con Vosk** (`vosk-model-small-es-0.42`, 58 MB, Apache-2.0) y no openWakeWord: la palabra debe ser el nombre del asistente, «Aria», y no hay modelo de openWakeWord para «Aria» ni forma razonable de entrenarlo sin GPU. Vosk con gramática cerrada sirve para cualquier palabra española. Con la gramática mínima `["aria","oye aria","[unk]"]` todo se forzaba a «aria» (María, área, Ariadna, varias, «esta aria de ópera» la activaban con confianza 1,0). Solución medida: (1) palabras **señuelo** que suenan parecido (maría, marina, ariadna, varias, amplia, ópera...) y palabras cortas frecuentes (el, la, de, que...); «área» NO se usa como señuelo porque Vosk le asigna el propio «Aria»; (2) «Aria» solo cuenta si es la **primera palabra de una frase** de Vosk (tras una pausa), con `conf ≥ 0,6`; (3) enfriamiento de 2 s tras cada orden. La gramática necesita `json.dumps(..., ensure_ascii=False)` o Vosk ignora las palabras con tilde.
- **Resultado con frases de Piper (dos voces)**: 8/8 activaciones («Aria, ¿qué tiempo hace en Ronda?», «Aria.», «Oye Aria, pon música.», «Aria, ¿qué hora es?») y 0/16 falsas («María, ¿qué tiempo hace?», «El área de la cocina es grande.», «La habitación es amplia.», «Me encanta esta aria de ópera.», «Ariadna vendrá mañana...», «Varias personas...», «¿Qué tiempo hace en Ronda?», «Hola, buenos días...»). Por WebSocket a través de Caddy: 3/3 y 0/9, también «Aria» + pausa de 0,8 s + pregunta.
- **Fin de la orden** por energía (RMS > 3 × fondo, mínimo 400) con 0,8 s de silencio, 6 s sin hablar = cancelar, 12 s máximo. El audio reciente (20 s) solo está en RAM para recortar lo dicho tras «Aria». Ojo: `KaldiRecognizer.Reset()` no reinicia las marcas de tiempo de Vosk; el contador de muestras es acumulado.
- **Manos libres en el navegador**: AudioWorklet que diezma a PCM 16 kHz int16 (bloques de 80 ms) y WebSocket `/api/voz/despertar`. El middleware HTTP de Starlette no se ejecuta en WebSocket: el endpoint exige Origin igual al Host, cookie válida y rol permitido (cierra con 1008 → el navegador recibe 403), una escucha por usuario (1013) y dos en total en `aria-voz`. Mientras ARIA transcribe y habla no se envía audio (evita que se oiga a sí misma); al ocultar la pestaña se apaga.
- **Seguridad**: `Permissions-Policy: microphone=(self), camera=(), geolocation=()` en la app (lo que ve el túnel de Cloudflare) y en Caddy con `?` (solo si falta, para no duplicarla). CSP sin cambios: el WebSocket va a `'self'` y no hubo ninguna violación en Chromium.
- **Contexto seguro**: verificado con Chromium sin cabeza: `isSecureContext` y `navigator.mediaDevices` presentes en `https://192.168.1.50` (Caddy, certificado propio) y en `https://aria.tu-dominio.com` (certificado válido; hoy redirige a Cloudflare Access sin sesión).
- **Dependencias**: `av<19` (PyAV 19 quitó `metadata_errors`, que usa faster-whisper 1.2.1), `libatomic1` para `libvosk.so` en arm64, `websockets` en la app (uvicorn lo necesita para servir WebSocket y la app lo usa como cliente hacia `aria-voz`).

### Medidas en la Pi (2026-10-07, proyecto de prueba `aria-voz`)
- Groq STT de «Aria, ¿qué tiempo hace en Ronda?» (voz sharvard): 0,32-0,42 s por la API de ARIA → «Aria, ¿qué tiempo hace en Onda?».
- Whisper local base (con Groq forzado a fallar por clave inválida → relevo real): 3,3-4,6 s → «¿Area qué tiempo hace en Ronda?».
- Manos libres de extremo a extremo: el texto llega 0,4-1,1 s después de terminar de hablar (0,8 s de silencio + ~0,35 s de Groq).
- `aria-voz`: RSS 47 MB en reposo; 182 MB con una escucha (Vosk cargado); ~680 MB con Whisper base, Piper y Vosk cargados. CPU con una escucha: ~6 % de un núcleo (máx. 8-10 %). `aria-app` ~69 MB.
- Chromium sin cabeza (`--use-fake-device-for-media-stream` con un WAV de «Aria, ¿qué hora es?»): pulsar para hablar → transcripción → respuesta; «Leer» reproduce con Piper; manos libres hizo tres ciclos completos (escuchando → te escucho → transcribiendo → respondiendo → escuchando) como admin y como usuario; «Dejar de escuchar» y ocultar la pestaña apagan el micrófono; 0 violaciones de CSP y 0 errores de consola.

## Decisiones de la cadena de cerebros (2026-10-07)
- **Cadena Ollama Cloud → Groq → Gemini → local**, todo gratuito. Cada fallo (429/cuota, clave, modelo, timeout, red) pasa al siguiente; la cuota se recuerda 15 min (o `Retry-After`), clave/modelo 30 min, red/timeout 60 s. Esperas solo en memoria; orden y activación en `data/cerebros.json`.
- **Ollama Cloud por defecto `gpt-oss:120b-cloud`**: medido desde `aria-app` con herramientas, 120b dio primer token 0,3-0,4 s (2,0 s con llamada a herramienta una vez) frente a 2,0-3,2 s de 20b; ambos llaman bien a las herramientas. El razonamiento llega en `message.thinking` y se descarta.
- **Gemini por defecto `gemini-3.1-flash-lite`**: `gemini-2.5-flash` (y 2.5-flash-lite) responden 404 «no longer available to new users» aunque aparezcan en el listado; `gemini-flash-latest` tardó 12 s. Los modelos Gemini 3 devuelven `thought_signature` en `extra_content` de cada tool_call y hay que reenviarlo.
- **Groq**: sin clave en esta instalación, no probado en real (solo pruebas unitarias del adaptador OpenAI). Por defecto `openai/gpt-oss-120b`.
- Herramientas: las nubes reciben todas; `relevantes()`/`rescatar_llamada()` solo para el local. Mensajes internos en formato Ollama, convertidos al vuelo.
- Con la nube, los mensajes salen de casa (Google puede usarlos para mejorar productos en el plan gratuito); el local sigue siendo 100 % privado.
- Latencias reales (LAN, 2026-10-07, primer token / total): «Hola» Ollama Cloud 0,5/0,6 s, Gemini 1,0/1,1 s, local 0,8-1,2/4,5-5,3 s; «temperatura de la Raspberry» (con herramienta) Ollama Cloud 0,8/0,9 s, Gemini 3,3/3,4 s, local 20/28-32 s; «anuncios bloqueados» Ollama Cloud 1,1/1,3 s, Gemini 2,3/2,3 s, local 15-26/34-48 s. «Probar»: Ollama Cloud 0,5 s, Gemini 1,0 s, local 2 s (modelo caliente).

## Decisiones de usuarios y SSO (2026-10-07)
- SSO por JWT verificado de Cloudflare Access (PyJWT[crypto], JWKS en caché 1 h, refresco en `kid` desconocido con espera de 30 s). Nunca se usa la cabecera de email. Cloudflare caído = fallo transitorio («Entrando…»); sin JWT en el dominio público = formulario de respaldo.
- Usuarios en la tabla `usuarios` de `data/aria.db`; sesión = id + versión por usuario (cambiar contraseña, desactivar o reactivar la invalida). Las cookies del admin único anterior siguen valiendo hasta que cambie su contraseña.
- Migración: se hizo copia en `data/aria.db.bak-sso` antes de migrar. El admin `admin` toma el primer email de `ARIA_ADMIN_EMAILS`, su hash de `data/auth.json` (si lo había) o `ARIA_PASSWORD`, y todas las conversaciones existentes. `data/auth.json` ya no se usa tras migrar.
- Cada email de `ARIA_ADMIN_EMAILS` es un usuario distinto: el segundo (usuario) se crea vacío, sin las conversaciones del primero. No hay alias entre emails.
- Permisos del rol `usuario` por lista blanca (`permisos.py`); el resto es solo admin. El chat de un usuario solo ofrece herramientas de consulta. No se sincronizan políticas de Cloudflare (sin tokens de Cloudflare en ARIA).

## Decisiones de v2.0.0
- **Un único centro de control**: Inicio (lanzador), Chat, Centro de control y Ajustes en una SPA sin build (scripts clásicos, hash routing). Iconos SVG en línea (las fuentes de emoji no están garantizadas).
- **SHIELD-DNS por API de Pi-hole v6**: un solo `sid` en memoria, reautenticación solo ante 401, `DELETE /api/auth` al apagar (Pi-hole limita las sesiones).
- **HEIMDALL por API de wg-easy v15**: `verify=False` (certificado autofirmado accedido por IP) y lista blanca de campos: `privateKey`, `preSharedKey` y `publicKey` nunca salen del servidor; el `.conf` solo como descarga autenticada.
- **Crear/activar/desactivar VPN es herramienta del modelo; borrar no** (solo interfaz con confirmación). La creación por chat no muestra claves: devuelve el id y el chat ofrece «Ver QR».
- **Conversaciones en SQLite** (`data/aria.db`, WAL): el servidor guarda mensajes y el cliente solo envía id + mensaje; lo generado se guarda aunque se pulse Detener.
- **Contraseña**: hash scrypt con sal en `data/auth.json` (0600) con prioridad sobre `ARIA_PASSWORD`; una «versión de sesión» invalida las demás sesiones.
- **Modelo activo** en `data/model.txt`; descargas limitadas a una lista curada.
- **CSRF**: `Referrer-Policy: no-referrer` hacía que Chrome enviase `Origin: null` en formularios same-origin y el login fallaba. Ahora `Origin: null` solo se acepta con `Sec-Fetch-Site: same-origin` (o Referer coincidente); Caddy usa `strict-origin-when-cross-origin`.
- **Contraseñas de paneles**: `POST /api/secret/{shield|vpn}` las entrega a sesiones autenticadas (botón «Copiar contraseña»); documentado en el README.
- **Bug corregido**: el renderizador de Markdown usaba una regex global compartida en una función recursiva (bucle infinito con negrita). Ahora una instancia por llamada y prueba `md.test.js`.
- Herramientas nuevas: `_INTENCIONES` con exclusiones («!patrón») para que «pausa el bloqueador» no ofrezca Spotify y las preguntas conceptuales («explícame qué es la RAM») no activen `estado_sistema`.

## Mapa de puertos
| Proyecto | Puertos |
|---|---|
| ARIA | 80, 443 |
| SHIELD-DNS | 53, 8080, 8443 |
| HEIMDALL | 51820/udp, 51843 |

## Limitaciones conocidas
- Voz: no se ha probado a través del túnel de Cloudflare ni con un micrófono real (solo con el dispositivo falso de Chromium y frases de Piper); Cloudflare admite WebSocket. La detección de «Aria» con voces reales y ruido de casa puede necesitar ajustar `VOZ_CONFIANZA`. Whisper local base comete errores con nombres propios («Ronda»). Groq gratuito tiene límites por hora; al agotarlo se usa el local (más lento).
- Spotify requiere Premium y un dispositivo activo; el flujo OAuth completo no se ha podido probar sin credenciales reales (sí la ruta "no configurado").
- El modelo 3B usaba herramientas sin motivo (consultaba la hora al saludar o Spotify al pedir un chiste) y a veces escribía la llamada como JSON mal formado en el texto. Solución aplicada: `tools.relevantes()` solo ofrece las herramientas cuyas palabras clave aparecen en el mensaje (`_INTENCIONES`) y `tools.rescatar_llamada()` convierte ese JSON en una llamada real. Tras el cambio, 12 de 12 pruebas correctas (saludos, chiste, explicación, hora, estado, Netflix, Spotify).
- El modelo 3B inventa datos cuando se le pide conocimiento concreto (p. ej. recomendó una película de Netflix inexistente). Es una limitación del tamaño del modelo.
- `mem_limit` se ignora en esta Pi (kernel sin cgroup de memoria).
- Latencia: la primera respuesta tras cargar el modelo tardó ~57 s.
- Limitador de login solo en memoria (las conversaciones sí se guardan en SQLite).
- El modelo 3B resume mal a veces el resultado de las herramientas (p. ej. confundió «disco ocupado» con «libre»; los textos de las herramientas se han hecho más explícitos) y responde de forma torpe tras crear/desactivar dispositivos VPN, aunque la acción se ejecuta bien.
- Los botones «Copiar contraseña» exponen las claves de Pi-hole y wg-easy a cualquier administrador de ARIA (los usuarios normales no los ven ni pueden pedirlas).
- RAM observada (Pi de 8 GB con escritorio y otros contenedores): con el modelo cargado, ~5,8 GiB usados y ~2,1 GiB disponibles (antes de cargar: ~3,5 GiB usados).

## Registro de cambios
- **2026-10-07 · voz**: micrófono (pulsar para hablar) en el chat y en Inicio, transcripción Groq Whisper con relevo a Whisper local, voz natural con Piper («Leer» y lectura automática, con la del navegador de respaldo), modo «manos libres» con la palabra «Aria» (Vosk) por WebSocket, Ajustes → Voz, contenedor `aria-voz` aislado y `Permissions-Policy`. Pruebas `test_voz.py`. Se quitaron las referencias a otros asistentes: en la interfaz y la documentación el asistente es siempre ARIA.
- **2026-10-07 · usuarios y SSO**: inicio de sesión único con Cloudflare Access, varios usuarios con roles admin/usuario aplicados en el servidor, conversaciones por usuario, Ajustes → Usuarios y herramientas de solo lectura para usuarios. Copia previa en `data/aria.db.bak-sso`. Verificado: login LAN de admin y de un usuario de prueba (403 en endpoints de admin, sin ver conversaciones ajenas; usuario y conversaciones de prueba borrados), la URL pública sigue devolviendo el 302 de Access y una petición interna con email falsificado y sin JWT no inicia sesión.
- **2026-10-07 · v2.0.0**: ARIA pasa a ser el centro de control del laboratorio: Inicio con lanzador, Centro de control (SHIELD-DNS, HEIMDALL, Sistema, Spotify), nuevas herramientas (bloqueador, VPN, sistema, gestión de dispositivos), conversaciones persistentes, selector de modelos, voz opcional, cambio de contraseña, manifest/icono, `update.sh` y `backup.sh`, pruebas pytest y corrección CSRF con `Origin: null`. RAM observada con la v2 en marcha (Pi de 8 GB, modelo descargado de memoria): ~2,9 GiB usados y ~5,0 GiB disponibles; `aria-app` ~41 MiB de RSS.
- **2026-10-06**: selección de herramientas por intención, rescate de llamadas en JSON, textos con tildes, mensaje de Spotify que no pide claves por el chat.
- **2026-10-06**: reescritura completa. Docker Compose (ollama, app, caddy), login, chat con streaming y bucle de herramientas, panel de servicios, Spotify, instalador/desinstalador, documentación en español.
- **2026-10-07 (revisión)**: nombres de dispositivos VPN con tildes/ñ; «desactiva el dispositivo X» funciona sin decir «VPN»; instalar-todo.sh y docs/GUIA.md; flujo «Añadir dispositivo → QR» probado con clics en Chromium sin errores de consola.
- **2026-10-07**: Ajustes → Certificado: descarga del certificado raíz público de Caddy (install.sh lo copia a data/). Verificado: con él, curl entra sin -k por IP y por .local.
- **2026-10-07 · cerebros**: cadena multi-proveedor (Ollama Cloud, Groq, Gemini, local) con relevo automático, esperas por cuota, adaptador OpenAI para herramientas, insignia del cerebro en cada respuesta, Ajustes → Cerebros (orden, activar, Probar), `ARIA_NOMBRE_USUARIO` (saludo y prompt) y pruebas pytest con proveedores falsos.
- **2026-10-07**: acceso público con Cloudflare Tunnel + Access (cloudflare/configurar.sh, idempotente, probado). Los enlaces a los paneles siguen al dominio público. Verificado: los tres nombres devuelven 302 a la pantalla de Access sin sesión.
- **2026-10-07**: cloudflare-ddns mantiene vpn.tu-dominio.com → IP pública (sin proxy); HEIMDALL usa ese host. Router: reserva 192.168.1.50, DNS de la casa = Pi, UDP 51820 → Pi.
- **2026-10-07**: plan B ante caídas: DNS secundario AdGuard en el router, autoheal (systemd timer) y watchdog; alerta de Cloudflare por email. Probado: autoheal reinicia un contenedor unhealthy. Descartado: fallback de upstream en Pi-hole con strict-order (se queda esperando a Unbound; la reserva del router ya cubre el caso).
- **2026-10-07**: los emails de ARIA_ADMIN_EMAILS son la misma persona (usuarios.canonico); al arrancar se fusionan duplicados (conversaciones al principal). Copia previa en data/aria.db.bak-fusion.
