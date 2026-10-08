# ARIA

ARIA es tu asistente doméstico local para Raspberry Pi. El modelo de lenguaje se ejecuta en tu propia máquina con [Ollama](https://ollama.com): **sin APIs de pago y sin enviar tus conversaciones a la nube**.

Incluye:

- **Inicio**: saludo, lanzador de aplicaciones con su estado en vivo (Chat, SHIELD-DNS, HEIMDALL), acciones rápidas y estado de la Pi.
- **Chat** con conversaciones guardadas, streaming, botón Detener, copiar, Markdown seguro y **voz**: micrófono (pulsar para hablar), «Leer» en cada respuesta con una voz femenina natural (Gemini «Leda», con respaldo en la Pi) y modo **manos libres** diciendo «Aria». Herramientas: hora, bloqueador de anuncios, VPN, estado de la Raspberry, búsqueda en internet, tiempo, recordatorios y memoria. Spotify y Netflix están aparcados para más adelante (`ARIA_SPOTIFY=1` / `ARIA_NETFLIX=1` los reactivan).
- **Centro de control** para [SHIELD-DNS](https://github.com/BertMarti/SHIELD-DNS) (Pi-hole), [HEIMDALL](https://github.com/BertMarti/HEIMDALL) (VPN WireGuard) y el sistema.
- **Ajustes**: modelos, voz (micrófono, leer en voz alta, manos libres, velocidad), cambio de contraseña, avisos y versión.
- **HTTPS** automático (certificado propio de Caddy), acceso con usuario y contraseña, y se puede añadir a la pantalla de inicio del móvil.

## Guía rápida de uso

1. **Entrar.** Abre `https://<IP-de-la-Pi>`, acepta el aviso del certificado (es lo esperado) e inicia sesión. Para tenerla como app, en el móvil usa «Añadir a pantalla de inicio».
2. **Inicio.** Es la página por defecto. Arriba escribe en «Pregúntale a ARIA» para abrir un chat con esa pregunta. Las cuatro fichas abren cada aplicación en una pestaña nueva (el punto indica si está activa, caída o sin instalar); en SHIELD-DNS y HEIMDALL, «Copiar contraseña» te evita teclearla en su panel. Debajo tienes las acciones rápidas y el estado de la Pi.
3. **Chat.** Escribe en la parte inferior; «Detener» corta la respuesta, «Copiar» copia un mensaje. A la izquierda (☰ en el móvil) están tus conversaciones: «+ Nueva», ✎ renombrar y ✕ borrar. Prueba: «¿Cuántos anuncios has bloqueado hoy?» o «¿Qué temperatura tiene la Raspberry?».
4. **Centro de control.** Tarjetas de SHIELD-DNS, HEIMDALL y Sistema; se actualizan solas cada 15 s.
5. **Añadir un móvil a la VPN.** Centro de control → HEIMDALL → «Añadir dispositivo» (o la acción rápida de Inicio, o pídeselo al chat: «añade un dispositivo a la VPN llamado movil-ana»). Escribe un nombre, pulsa Crear y escanea el QR con la app WireGuard del móvil (o «Descargar .conf»). Con «QR» en la lista lo vuelves a ver; «Eliminar» pide confirmación.
6. **Pausar el bloqueador.** Centro de control → SHIELD-DNS → «Pausar 5/30/60 min» (o en Inicio, o en el chat: «pausa el bloqueador 10 minutos»). «Reanudar» lo reactiva antes de tiempo.
7. **Cambiar la contraseña.** Ajustes → Contraseña: actual, nueva (mínimo 10 caracteres) dos veces. Se guarda cifrada en `data/` y tiene prioridad sobre `ARIA_PASSWORD`; las sesiones de otros dispositivos se cierran.
8. **Cambiar de modelo.** Ajustes → Modelos: «Descargar» uno de la lista y luego «Usar». Con 8 GB, mejor modelos de 3B o menos.
9. **Actualizar.** `./update.sh` en la carpeta de ARIA.
10. **Copia de seguridad y restauración.** `./backup.sh` y los pasos de la sección anterior.

## Requisitos

- Raspberry Pi 5 (u otra máquina arm64/amd64) con 8 GB de RAM, Raspberry Pi OS o Debian/Ubuntu.
- Docker y `docker compose` v2 (si falta Docker, `install.sh` ofrece instalarlo con el script oficial).
- Unos 3 GB libres de disco para el modelo por defecto, y libres los puertos 80 y 443.

## Instalación

```bash
git clone https://github.com/BertMarti/ARIA.git && cd ARIA && ./install.sh
```

### Instalar todo el homelab de una vez (ARIA + SHIELD-DNS + HEIMDALL)

En una Raspberry recién instalada (o para actualizar las tres apps):

```bash
curl -fsSL https://raw.githubusercontent.com/BertMarti/ARIA/main/instalar-todo.sh | bash
```

Clona los tres repositorios en `~/homelab` y los instala en el orden correcto (SHIELD-DNS, HEIMDALL y ARIA, que detecta a los otros dos y se conecta a ellos). Con `COPIAS_AUTOMATICAS=1` delante programa además una copia de seguridad diaria de las tres apps a las 04:30. El uso de ARIA está explicado más abajo en este README.

### Qué hace `install.sh`

El script es idempotente: puedes relanzarlo sin problema. Hace lo siguiente:

1. Crea `.env` (si no existe) con una contraseña y un secreto aleatorios y detecta la IP de la LAN.
2. Construye y arranca los tres contenedores (`aria-ollama`, `aria-app`, `aria-caddy`).
3. Espera a que estén sanos y descarga el modelo (`ARIA_MODEL`). Con `SKIP_MODEL=1 ./install.sh` se omite la descarga; luego puedes hacerla desde el panel.
4. Muestra la URL y las credenciales.

## Primer acceso

Abre **https://aria.local** (la Pi lo anuncia por mDNS en tu red), `https://aria.lan` (si usas SHIELD-DNS o la VPN) o `https://<IP-de-la-Pi>` e inicia sesión con `ARIA_USER` / `ARIA_PASSWORD` de `.env` (en la primera arrancada se crea con ellos el administrador `admin`; también sirve su email). Después puedes cambiar la contraseña desde **Ajustes** (ver la guía rápida).

### Aviso de certificado

El navegador mostrará "la conexión no es privada". **La forma fácil de quitar el aviso:** ARIA → Ajustes → Certificado → «Descargar certificado» e instálalo en cada dispositivo (la tarjeta explica cómo en Windows, Android, iPhone, Mac y Firefox). Es normal: ARIA usa la autoridad certificadora interna de Caddy, que tu navegador no conoce. El tráfico va cifrado igualmente. Acepta la excepción (Avanzado → Continuar). Si quieres evitar el aviso, importa el certificado raíz que Caddy genera en el volumen `caddy_data` (`/data/caddy/pki/authorities/local/root.crt` dentro de `aria-caddy`) en tus dispositivos:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./aria-root.crt
```

Los certificados se emiten bajo demanda solo para los nombres/IPs listados en `ARIA_HOSTS` (`.env`). Si accedes con otro nombre, añádelo ahí y reinicia con `docker compose up -d`.

## Cerebros

ARIA no depende de un solo modelo: tiene una **cadena de cerebros gratuitos** que prueba en orden. Si uno falla (límite de uso gratuito, clave rechazada, sin conexión o más de 30 s sin responder), pasa al siguiente sin que lo notes; el que haya fallado por límite se salta durante 15 minutos (o lo que indique el proveedor). Cada respuesta lleva una insignia con el cerebro que la dio y la cabecera del chat muestra el que está en cabeza.

| # | Cerebro | Modelo por defecto | Clave | Coste |
|---|---------|--------------------|-------|-------|
| 1 | **Ollama Cloud** (a través del Ollama local) | `gpt-oss:120b-cloud` | tu cuenta de Ollama: `docker exec -it aria-ollama ollama signin` | 0 € (plan gratuito con límites) |
| 2 | **Groq** | `openai/gpt-oss-120b` | `GROQ_API_KEY` en `.env` (console.groq.com/keys) | 0 € |
| 3 | **Google Gemini** | `gemini-3.1-flash-lite` | `GEMINI_API_KEY` en `.env` (aistudio.google.com/apikey) | 0 € |
| 4 | **Local** | el de Ajustes → Modelos (`llama3.2:3b`) | ninguna | 0 €, funciona sin internet |

- **Dónde poner las claves:** `nano ~/homelab/ARIA/.env`, rellena `GROQ_API_KEY` y/o `GEMINI_API_KEY` y aplica con `docker compose up -d`. Si una clave está vacía, ese cerebro se omite. Las claves nunca se muestran en la web ni en los registros; Ajustes solo dice «clave configurada ✔» o «falta la clave».
- **Orden y activación:** Ajustes → **Cerebros** (flechas ↑↓, interruptor y botón **Probar**, que mide la latencia). Se guarda en `data/cerebros.json`, que manda sobre `ARIA_CEREBROS` del `.env`. El cerebro local no se puede desactivar: es el último recurso.
- **Modelos:** `ARIA_MODELO_OLLAMA_CLOUD`, `ARIA_MODELO_GROQ` y `ARIA_MODELO_GEMINI` en `.env`. Se eligió `gpt-oss:120b-cloud` porque respondió antes que `gpt-oss:20b-cloud` (0,3-0,5 s frente a 2 s hasta el primer token) con la misma calidad en llamadas a herramientas. `gemini-2.5-flash` ya no está disponible para cuentas nuevas de Google (error 404); se usa `gemini-3.1-flash-lite`.
- **Herramientas:** los cerebros de la nube reciben todas las herramientas y deciden cuándo usarlas; el modelo local pequeño solo recibe las relacionadas con las palabras de tu mensaje (así no las usa sin motivo). El borrado de dispositivos VPN sigue siendo solo de la interfaz.
- **Razonamiento:** los modelos `gpt-oss` envían su «pensamiento» aparte; ARIA nunca lo muestra como respuesta (solo un «pensando…» mientras llega).
- **Privacidad:** con el cerebro local nada sale de casa. Con Ollama Cloud, Groq o Gemini, **tus mensajes y los resultados de las herramientas (estado de la Pi, número de anuncios bloqueados, nombres de dispositivos VPN…) se envían a esas empresas** para generar la respuesta. En el plan gratuito de Google, además, **Google puede usar los mensajes para mejorar sus productos**. Si prefieres que todo se quede en casa, desactiva los tres primeros en Ajustes → Cerebros.
- Tratamiento: ARIA te llama por tu nombre (`ARIA_NOMBRE_USUARIO`; si está vacío, usa el nombre de tu usuario).

## Modelo local

El modelo por defecto es `llama3.2:3b` (unos 2 GB). En una Pi de 8 GB funciona, con una velocidad modesta. Desde **Ajustes → Modelos** puedes ver los instalados, cambiar el activo (se guarda en `data/model.txt` y tiene prioridad sobre `ARIA_MODEL`), descargar uno de la lista (`llama3.2:3b`, `llama3.2:1b`, `qwen2.5:3b`, `gemma2:2b`) con barra de progreso y borrar los que no uses (no se puede borrar el activo).

Consejos: los modelos más pequeños responden antes pero fallan más al usar herramientas; `gemma2:2b` no admite herramientas (ARIA lo detecta y responde sin ellas). `ARIA_NUM_CTX` y `OLLAMA_KEEP_ALIVE` en `.env` controlan la RAM usada.

## Herramientas del asistente

ARIA solo ofrece al modelo las herramientas cuyas palabras clave aparecen en tu mensaje (un modelo de 3B las usa sin motivo si se le dan todas), así que charlar o pedir explicaciones nunca las activa.

| Herramienta | Qué hace |
|---|---|
| `fecha_hora` | Fecha y hora actuales |
| `estado_servicios` | Estado de SHIELD-DNS y HEIMDALL |
| `estado_bloqueador`, `pausar_bloqueador(minutos)`, `reanudar_bloqueador` | Estadísticas de Pi-hole, pausa de 1 a 120 min y reanudación |
| `dispositivos_vpn` | Dispositivos de la VPN y cuáles están conectados (handshake < 3 min) |
| `crear_dispositivo_vpn(nombre)`, `activar_dispositivo_vpn(nombre)`, `desactivar_dispositivo_vpn(nombre)` | Gestión de dispositivos VPN por nombre. Al crear uno no se muestra ninguna clave en el chat: aparece un botón «Ver QR». **Borrar dispositivos solo se puede desde la interfaz, con confirmación.** |
| `estado_sistema` | Temperatura, RAM, disco, carga y tiempo encendida de la Pi |
| `spotify_play`, `spotify_pause`, `spotify_siguiente`, `spotify_anterior`, `spotify_actual`, `spotify_buscar_y_reproducir` | Control de Spotify |
| `buscar_en_netflix` | Devuelve un enlace de búsqueda en Netflix |
| `buscar_en_internet(consulta)`, `noticias(tema)` | Búsqueda en internet y titulares en español (lectura: también para el rol `usuario`) |
| `registrar_movimiento`, `resumen_mes`, `gastos_por_categoria`, `comparar_meses`, `presupuesto`, `estado_presupuestos`, `buscar_movimientos` | Agente Finanzas (datos del usuario que chatea) |
| `estado_red`, `dispositivos_red`, `dispositivos_nuevos`, `marcar_dispositivo_conocido`, `medir_latencia`, `test_velocidad` | Agente Redes (un usuario solo `estado_red`) |
| `informe_seguridad`, `escanear_red`, `estado_escaneo`, `bloqueos_por_cliente` | Agente Seguridad (solo admin) |
| `resumir_enlace(url)` | Lee una página web pública y la resume (ver «Compartir con ARIA y resumir enlaces») |
| `crear_rutina`, `mis_rutinas`, `borrar_rutina` | Rutinas programadas del usuario que chatea («crea una rutina…», «mis rutinas», «borra la rutina del tiempo») |

### Búsqueda en internet

ARIA busca con **SearXNG**, un metabuscador que corre en el contenedor interno `aria-searxng` (sin puertos publicados: solo la app lo alcanza). ARIA nunca habla directamente con los buscadores.

- Herramientas `buscar_en_internet` y `noticias` (titulares del último día, completados con los de la semana). Los cerebros en la nube las usan para lo reciente o lo que no saben y citan las fuentes al final («Fuentes: …»); el modelo local solo las recibe con palabras clave (busca, internet, noticias, precio, resultado, quién ganó, cuándo…).
- Resultados compactos (≤ 1 500 caracteres): título, dominio, extracto y enlace, sin parámetros de seguimiento, un resultado por dominio y caché de 10 minutos. El chat muestra «Buscando en internet…» y los enlaces a las fuentes.
- Configuración en `searxng/settings.yml` (idioma `es-ES`, búsqueda segura moderada, sin proxy de imágenes, limitador desactivado por ser interno). Motores sin clave: DuckDuckGo, Brave, Bing, Google, Wikipedia y de noticias DuckDuckGo/Bing/Google/Brave/Wikinoticias; si uno es bloqueado, responden los demás.
- `SEARXNG_SECRET` lo genera `install.sh` (o `update.sh` en instalaciones antiguas). `SEARXNG_MEM_LIMIT` limita su memoria (384 m por defecto; consume unos 150 MB).
- Privacidad: las consultas salen de tu casa hacia los buscadores desde la IP de la Pi, y el texto de los resultados llega al cerebro que uses (incluida la nube).

## Voz

Todo gratis: la transcripción usa la API gratuita de Whisper de Groq (con la misma `GROQ_API_KEY` de los cerebros) y, si falla, la Pi; la voz de ARIA y la palabra «Aria» funcionan en la propia Pi, en el contenedor `aria-voz`.

- **Pulsar para hablar**: el botón del micrófono (en el chat y en «Pregúntale a ARIA» de Inicio). Mantenlo pulsado mientras hablas y suéltalo, o tócalo una vez para empezar y otra para terminar. El texto aparece en la caja y se envía solo. Máximo 30 s.
- **Leer en voz alta**: botón «Leer» en cada respuesta, o Ajustes → Voz → «Leer las respuestas en voz alta». La voz es la femenina «Leda» de Gemini (gratis con `GEMINI_API_KEY`); si falla o se agota la cuota, se usa la femenina de Piper en la Pi (`ARIA_TTS=local` para usar siempre esta); si `aria-voz` no responde se usa la voz del navegador. Se leen como mucho 1500 caracteres, sin Markdown, código ni enlaces.
- **Manos libres**: botón «Manos libres» del chat (o Ajustes → Voz). Aparece un aviso fijo «Manos libres: escuchando "Aria"» con el botón **Dejar de escuchar**. Di «Aria» seguido de tu pregunta («Aria, ¿qué hora es?») o «Aria», una pausa corta y la pregunta. Suena un pitido, ARIA transcribe lo que dices hasta que haces una pausa, lo envía al chat y lee la respuesta. «Aria» solo cuenta al principio de una frase: «la habitación es amplia», «María» o «esta aria de ópera» no la activan. El micrófono se apaga al cambiar de pestaña o bloquear el móvil, y mientras ARIA responde no se envía audio.
- **Ajustes → Voz**: elegir micrófono y probarlo (barra de nivel), leer en voz alta, manos libres y velocidad de la voz. Se guardan en cada dispositivo.

**Requisitos**: el navegador solo deja usar el micrófono por HTTPS. Funciona en `https://aria.<tu dominio>` y en `https://<IP>`; en la LAN conviene instalar el certificado (Ajustes → Certificado) para no tener que aceptar el aviso. La primera vez el navegador pide permiso para el micrófono.

**Privacidad**: al hablar, el audio se envía a **Groq** para transcribirlo (si hay `GROQ_API_KEY`); si Groq falla, está en su límite gratuito o no hay clave, se transcribe en la Pi (Whisper `base`, más lento y menos preciso). En «manos libres» el sonido del micrófono va continuamente a la Pi (nunca fuera) para detectar «Aria»; solo lo que dices después de «Aria» se transcribe. **El audio no se guarda nunca** (ni en disco ni en la base de datos): se procesa en memoria y se descarta. Solo se guarda el texto, como cualquier mensaje del chat.

**Límites**: subidas de hasta 1 MB (audio WebM/Ogg/WAV/MP4/MP3 comprobado por su cabecera), 12 transcripciones por minuto y 200 por hora por usuario (`ARIA_VOZ_STT_MINUTO`, `ARIA_VOZ_STT_HORA`), una escucha «manos libres» por usuario y dos en total.

## Imágenes (visión)

ARIA puede mirar una foto y responder sobre ella, en el chat web y en Telegram.

- **Web**: botón de imagen junto a la caja de texto, o **pega** una captura (Ctrl+V) o **arrástrala** al chat. Antes de enviarla, el navegador la reduce (1600 px como máximo, JPEG) y la recodifica, lo que también quita los datos EXIF (ubicación GPS, cámara…). En tu mensaje se ve una miniatura. Puedes escribir una pregunta o enviarla sin texto («¿qué ves?»).
- **Telegram**: manda una foto (o una imagen como archivo), con o sin pie de foto. Se responde en el mismo chat, con los permisos de tu usuario.
- **Tickets → Finanzas**: si la foto es un ticket, una factura o un recibo (o pides «apúntalo»), ARIA lee comercio, fecha, total y categoría y **propone** apuntar el gasto. En la web sale una tarjeta con «Registrar gasto» / «Descartar»; en Telegram, botones «Registrar» / «Cancelar». Nada se apunta sin pulsar el botón, y siempre en tus finanzas (el usuario lo pone el servidor). La propuesta caduca a los 30 min en la web y a las 24 h en Telegram. Si algo se leyó mal, corrígelo después en Finanzas.

**Cerebros con visión**: Google Gemini (`gemini-3.5-flash-lite`) y, de respaldo, Groq (`qwen/qwen3.8-27b`), con las mismas `GEMINI_API_KEY` y `GROQ_API_KEY` de los cerebros. El modelo local no ve imágenes: si no hay ninguno disponible, ARIA lo dice. Se cambian con `ARIA_VISION` (orden; `no` la apaga), `ARIA_MODELO_VISION_GEMINI` y `ARIA_MODELO_VISION_GROQ`.

**Privacidad**: la imagen se envía a Google o a Groq (en el plan gratuito, Google puede usarla para mejorar sus productos). **La imagen no se guarda nunca** (ni en disco ni en la base de datos): en el historial queda «Imagen» con tu texto y la respuesta. Antes de enviarla, el servidor comprueba que es JPEG, PNG o WebP por sus bytes, que no pasa de 5 MB y le quita los metadatos (EXIF/GPS, XMP, IPTC, comentarios).

**Límites**: 6 imágenes por minuto y 60 por hora por usuario (`ARIA_VISION_MINUTO`, `ARIA_VISION_HORA`). La cuota gratuita de Groq para visión es pequeña: se gasta en pocas fotos seguidas y entonces se espera a que se recupere.

### Limitación con Netflix

Netflix **no tiene API pública**. ARIA no puede controlar su reproducción: solo genera un enlace `netflix.com/search?q=...` que tú abres.

## Spotify (opcional)

El control de reproducción de la Web API de Spotify **requiere una cuenta Premium**.

1. Entra en <https://developer.spotify.com/dashboard> y crea una app.
2. Añade como *Redirect URI* exactamente `https://<IP-de-la-Pi>/spotify/callback` (es el valor por defecto de `SPOTIFY_REDIRECT_URI`; Spotify exige HTTPS salvo para loopback).
3. Copia el *Client ID* y el *Client secret* a `SPOTIFY_CLIENT_ID` y `SPOTIFY_CLIENT_SECRET` en `.env`.
4. `docker compose up -d` y, en Ajustes → Spotify (o en el Centro de control), pulsa **Conectar Spotify**.
5. Debe haber un dispositivo con Spotify abierto (móvil, ordenador, altavoz) para que haya "dispositivo activo".

El token se guarda en `data/spotify_token.json` (ignorado por git).

## Integraciones del laboratorio

Se configuran en `.env` (todas opcionales; si faltan, la tarjeta aparece como «no conectado» con instrucciones):

| Variable | Descripción |
|---|---|
| `SHIELD_URL` | API de Pi-hole v6 (por defecto `http://<ARIA_LAN_IP>:8080`) |
| `SHIELD_PASSWORD` | Contraseña de Pi-hole (`PIHOLE_PASSWORD` en `../SHIELD-DNS/.env`) |
| `VPN_URL` | wg-easy de HEIMDALL (por defecto `https://<ARIA_LAN_IP>:51843`, certificado autofirmado) |
| `VPN_USER`, `VPN_PASSWORD` | Credenciales de administración (`WG_ADMIN_USER`, `WG_ADMIN_PASSWORD` en `../HEIMDALL/.env`) |

¿Quieres enchufar tu propia aplicación o función? Mira [docs/MODULOS.md](docs/MODULOS.md) (módulos en `modulos/`).

`install.sh` las rellena solo si están vacías y existen `../SHIELD-DNS/.env` y `../HEIMDALL/.env` (se leen con `grep`, nunca se ejecutan). Tras editar `.env`: `docker compose up -d`.

Seguridad: las claves privadas de WireGuard nunca llegan al navegador salvo el `.conf` que tú descargas expresamente. **Aviso:** los botones «Copiar contraseña» de Inicio entregan la contraseña de Pi-hole y de wg-easy a cualquier persona que haya iniciado sesión en ARIA (solo mediante una petición autenticada y sin caché; no van en el HTML). Protege bien la contraseña de ARIA.

## Memoria

ARIA recuerda cosas tuyas entre días y las usa para darte contexto.

- **Recuerdos** (máx. 300 caracteres, 200 por persona). Dile «recuerda que mi equipo es el Betis» (u «olvida que…»), o añádelos en **Ajustes → Memoria**, donde también puedes verlos, editarlos y borrarlos. Cada persona ve solo los suyos.
- **Aprendizaje automático** (activado por defecto; interruptor en Ajustes → Memoria): tras cada mensaje, en segundo plano y solo con un cerebro de la nube (nunca el local), ARIA extrae como mucho 3 datos personales duraderos. No guarda contraseñas, claves, tokens, tarjetas ni documentos de identidad. Con el tope de 200 se descartan primero los automáticos menos usados. Con el interruptor apagado no aprende nada ni escribe el diario.
- **Diario**: cada madrugada (03:30, `ARIA_TZ`) un cerebro de la nube resume en 3–5 viñetas lo que hiciste ese día (sin nube: títulos de las conversaciones). Al arrancar recupera los días perdidos (hasta 14). Ajustes → Memoria muestra los últimos 14 días y deja borrar cada uno.
- **Privacidad**: la memoria se envía a los cerebros en la nube (Ollama Cloud, Groq, Gemini) junto con tus preguntas (hasta ~1 200 caracteres de recuerdos y ~900 del diario). El cerebro local recibe como máximo ~300 caracteres y nada del diario. «Borrar toda mi memoria» elimina recuerdos y diario.

## Resumen de buenos días

- En **Inicio**, la tarjeta «Tu resumen de hoy» (se puede cerrar por hoy o actualizar) reúne: saludo y fecha, el resumen de ayer, anuncios bloqueados ayer (Pi-hole), dispositivos VPN y cuáles se conectaron en 24 h, temperatura/RAM/disco de la Pi, la última copia fuera de la Pi y 1–2 recuerdos que pueden venir al caso. Los datos de VPN y copias solo los ve el administrador.
- En el **chat**, el primer «hola» / «buenos días» de cada día se responde con una versión hablada del resumen.
- `GET /api/briefing` (caché por usuario y día; `?refrescar=1` lo regenera).
- La copia fuera de la Pi se lee con `git log` del repositorio `ARIA_COPIAS_REPO` (por defecto `/home/usuario/homelab/.copias-repo`) solo si está montado en el contenedor; si no, pone «no disponible».
- **Tiempo (opcional)**: rellena `ARIA_CIUDAD` (p. ej. `"Ronda, Málaga"`; con «, Provincia» elige el resultado de España de esa provincia) y se usa Open-Meteo (gratis, sin clave) para temperatura actual, máxima/mínima y probabilidad de lluvia. `ARIA_LAT` y `ARIA_LON` fijan las coordenadas y evitan geocodificar; si no, se geocodifica una vez y se guarda en `data/ciudad.json`. Vacío por defecto = sin tiempo.

## Avisos y recordatorios

ARIA vigila la casa en segundo plano (un planificador dentro de la app, sin contenedor nuevo) y te avisa por la **campana** de la cabecera y, si los activas, por **Telegram** y por **notificaciones en el móvil o el navegador**.

| Aviso | Cada | Gravedad |
|---|---|---|
| SHIELD-DNS caído o sin responder al DNS; HEIMDALL caído | 1 min (2 seguidos) | grave |
| No se puede entrar desde fuera (`ARIA_URL_PUBLICA` no da 200/302: túnel de Cloudflare) | 5 min (2 seguidos) | aviso |
| Dispositivo desconocido nuevo en la LAN (inventario de Red) | 10 min | aviso |
| Hallazgo de gravedad alta en el último escaneo de seguridad | 15 min | grave |
| Copia fuera de casa de hace más de 36 h (`data/ultima-copia.json`) | 30 min | aviso |
| Raspberry a más de 75 °C, disco por encima del 85 %, menos del 5 % de RAM disponible | 1–10 min | grave / aviso |
| Un dispositivo se conecta a la VPN (apagado por defecto) | 1 min | info |
| Solo responde el cerebro local durante más de 30 min | 1 min | aviso |

- Cada aviso tiene una clave para no repetirse, un tiempo mínimo entre avisos iguales y un mensaje de «todo en orden» cuando se arregla. Lo que ya existía al instalar (dispositivos, hallazgos, conexiones VPN) no se avisa.
- Los avisos de la casa solo llegan a los administradores. En **Ajustes → Avisos** cada usuario elige qué tipos quiere, por qué canales, sus **horas de silencio** (por defecto 23:00–08:00; los graves y los recordatorios llegan igual) y el **resumen de buenos días** por Telegram o notificación (por defecto a las 08:00). «Probar avisos» manda uno de prueba.
- **Recordatorios**: pídeselos a ARIA en el chat o por Telegram («recuérdame mañana a las 9 llamar al taller», «avísame en 20 minutos», «todos los lunes a las 8 sacar la basura»; repetición diaria, semanal o de lunes a viernes). «¿Qué recordatorios tengo?» y «borra el recordatorio 3» también funcionan. Se ven y se añaden en Ajustes → Recordatorios. Cada usuario solo ve los suyos.

## Rutinas

Tareas que ARIA hace sola a su hora y te manda el resultado: «cada mañana a las 8, dime el tiempo de hoy en Ronda y 3 titulares de tecnología».

- **Dónde**: Ajustes → **Rutinas** (crear, editar, pausar, borrar y «Ejecutar ahora»), en el chat («crea una rutina que de lunes a viernes a las 7:30 me diga…», «¿qué rutinas tengo?», «borra la rutina del tiempo»), en Telegram con `/rutinas` (botones «Ejecutar ahora» y «Pausar») y con **Ctrl+K / ⌘K** («Ejecutar rutina…»).
- **Cuándo**: todos los días a una hora, ciertos días de la semana («los lunes y jueves a las 9», «de lunes a viernes», «los fines de semana») o cada N horas (mínimo cada hora).
- **Cómo se ejecuta**: el prompt pasa por el mismo chat que la web, como tú (tu rol, tus agentes y tu memoria), con el agente elegido (ARIA, Finanzas, Redes o Seguridad, este solo admin). **Solo con cerebros en la nube**: si solo responde el local, se salta y te deja una nota en la campana. Máximo 90 s por ejecución y dos a la vez.
- **Solo consultan**: una rutina solo recibe herramientas de lectura (tiempo, noticias, búsqueda, estado de la casa, de la red, de tus finanzas…). Nunca pausa el bloqueador, toca la VPN, apunta gastos, escanea, mide la velocidad ni crea o borra recordatorios, rutinas o recuerdos.
- **Entrega**: por Telegram, notificación, los dos o solo la campana; siempre queda en la campana (sin horas de silencio: la pides tú). El resultado completo queda en la conversación «Rutina · nombre» (la de la vez anterior se sustituye salvo que hayas seguido hablando en ella).
- **Límites**: 10 rutinas por usuario. Nunca se ejecuta dos veces la misma hora programada aunque ARIA se reinicie; si ARIA estuvo apagada más de 3 h, esa ejecución se salta. Cada usuario solo ve, ejecuta y edita las suyas.

## Compartir con ARIA y resumir enlaces

- **Desde el móvil**: con ARIA instalada como aplicación (Chrome en Android: menú → Instalar aplicación / Añadir a pantalla de inicio), aparece **ARIA** en el menú **Compartir** de cualquier app. Al compartir un enlace o un texto se abre el chat con lo compartido y eliges «Resume esto» o «¿Qué opinas?». (Si ya la tenías instalada, desinstálala y vuelve a instalarla para que el móvil vea la opción. Safari en iPhone no admite este menú para webs instaladas.)
- **En el chat**: pega un enlace y pide «resúmelo». **En Telegram**: si mandas solo un enlace, ARIA ofrece el botón «Resumir».
- **Seguridad**: la página la descarga el servidor con protección anti-SSRF: solo http/https en los puertos 80/443, sin usuario:contraseña, el nombre debe resolver solo a IP públicas (nada de la LAN, 127.x, 169.254.x, 100.64.x, IPv6 locales…), la conexión va a esa IP ya comprobada (contra el *DNS rebinding*), cada redirección (máx. 3) se vuelve a comprobar, 15 s y 1,5 MB como mucho, solo HTML o texto. El texto llega al modelo marcado como contenido externo que no debe obedecer.

## Atajo de teclado

**Ctrl+K** (⌘K en Mac) abre la paleta de órdenes: ir a cualquier sección, conversación nueva, activar o desactivar manos libres y ejecutar una rutina. ↑/↓ para moverse, Intro para elegir, Esc para cerrar.

## Telegram

Bot propio de ARIA, con *long polling* (sin webhook: no se abre nada nuevo a Internet).

1. En Telegram, habla con **@BotFather** → `/newbot` → ponle nombre (ARIA) y un usuario acabado en `bot`. Copia el token.
2. Ponlo en `.env`: `TELEGRAM_BOT_TOKEN=…` y aplica con `docker compose up -d`.
3. Comprueba: `docker compose exec app python -m aria.telegram --probar` (muestra el @usuario del bot).
4. En **Ajustes → Avisos → Telegram**, «Vincular Telegram» da un código de 6 cifras (10 min, un solo uso) y un enlace `https://t.me/<bot>?start=<código>`. Ábrelo y pulsa Iniciar. Puedes vincular varios chats y desvincularlos.

En el chat vinculado puedes escribir, mandar **fotos** (ver «Imágenes»; los tickets se pueden apuntar con un botón) o **notas de voz** (se transcriben y, si lo activas, ARIA también responde con voz). Pasa por el mismo chat que la web: agentes, memoria, herramientas y permisos de tu usuario; cada chat tiene su conversación («Telegram · …» en el historial) y `/nuevo` empieza otra. Comandos: `/estado`, `/resumen`, `/tiempo [ciudad]`, `/recordatorios`, `/gastos`, `/vpn`, `/anuncios` (con botones de pausa, solo admin), `/nuevovpn <nombre>` (admin: crea el dispositivo y manda el QR y el `.conf`, que contiene la clave privada), `/desvincular`, `/ayuda`. Las acciones de administración piden «Confirmar». Los chats no vinculados solo reciben «No te conozco…» y los grupos se ignoran.

## Notificaciones en el móvil

Notificaciones push estándar (Web Push con VAPID; `install.sh` genera `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` si faltan).

- Entra por **https://aria.tu-dominio.com** (certificado válido; por la IP de casa no funcionan) y en **Ajustes → Avisos** pulsa «Activar notificaciones en este dispositivo». Se listan tus dispositivos (puedes quitarlos) y «Enviar notificación de prueba».
- **iPhone/iPad**: iOS 16.4 o posterior y ARIA añadida a la pantalla de inicio (Safari → Compartir → Añadir a pantalla de inicio); actívalas abriendo ARIA desde ese icono.
- El mensaje viaja cifrado por el servicio push del navegador (Google, Mozilla, Apple o Microsoft; no se admite ningún otro destino). Las suscripciones caducadas se borran solas. El service worker (`/sw.js`) solo muestra notificaciones y abre ARIA en la página del aviso: no guarda páginas en caché.

## Acceso desde cualquier lugar (dominio propio + Cloudflare)

Con un dominio en Cloudflare, ARIA, Pi-hole y el panel de la VPN quedan en `https://aria.TUDOMINIO`, `https://shield.TUDOMINIO` y `https://heimdall.TUDOMINIO`, con certificado válido, **sin abrir puertos** y protegidos por **Cloudflare Access**: primero un código que llega a tu email y luego la contraseña de cada app. La sesión de Access dura 30 días por dispositivo.

1. En Cloudflare: compra o añade el dominio, activa **Zero Trust (plan Free)** y añade el método de acceso **One-time PIN** (*Zero Trust → Integrations → Identity providers → Add → One-time PIN*).
2. Crea un API token con *Zone·DNS·Edit*, *Account·Cloudflare Tunnel·Edit* y *Account·Access: Apps and Policies·Edit*.
3. En la Raspberry, rellena `~/homelab/cloudflare.env` (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `DOMINIO`, `EMAIL_ACCESO`, varios emails separados por comas) y ejecuta:
   ```bash
   ./cloudflare/configurar.sh
   ```
   Crea el túnel, las rutas, la protección y los nombres, y arranca el conector (`cloudflare-tunnel`). Se puede repetir sin problema.

El mismo comando arranca también `cloudflare-ddns`, que mantiene **`vpn.TUDOMINIO`** apuntando a tu IP pública (sin proxy, porque la VPN va directa a tu router por UDP 51820). En HEIMDALL, pon esa dirección como *Host* en *Administración* para que los perfiles de los dispositivos no dependan de una IP que puede cambiar.

Los accesos directos de ARIA se adaptan solos: si entras por `aria.TUDOMINIO`, los paneles se abren por `shield.`/`heimdall.TUDOMINIO`; en casa, por la IP.

## Inicio de sesión único

Por el dominio público (`https://aria.TUDOMINIO`) ARIA no pide contraseña: reconoce a la persona que Cloudflare Access ya ha identificado (código por email o Google). ARIA **verifica la firma** del JWT que Cloudflare añade a cada petición (`Cf-Access-Jwt-Assertion`: RS256, `aud`, `iss`, caducidad y email); la cabecera de email por sí sola no vale nada. Si el email es de un usuario activo de ARIA, entra directamente; si no, ve «Tu cuenta (email) no tiene acceso a ARIA. Pide al administrador que te invite.».

En `.env` (con `ARIA_CF_ACCESS_TEAM` o `ARIA_CF_ACCESS_AUD` vacíos el SSO queda desactivado):

| Variable | Qué es |
|---|---|
| `ARIA_CF_ACCESS_TEAM` | Dominio de tu equipo, p. ej. `mi-equipo.cloudflareaccess.com` |
| `ARIA_CF_ACCESS_AUD` | Etiqueta AUD de la aplicación ARIA (Zero Trust → Access → Applications → ARIA) |
| `ARIA_ADMIN_EMAILS` | Emails siempre administradores; se crean solos en su primer acceso |

«Salir» por el dominio público borra la sesión de ARIA y cierra también la de Cloudflare Access. En casa (`https://<IP>`, `aria.local`, `aria.lan`) no interviene Cloudflare y se entra con usuario o email y contraseña como siempre. Las claves públicas de Cloudflare se guardan una hora en memoria y se vuelven a pedir si aparece una clave desconocida.

## Usuarios

ARIA admite varios usuarios con dos roles:

- **Administrador**: todo (Inicio, Chat, Centro de control, Ajustes completos y gestión de usuarios).
- **Usuario**: Inicio (solo estado, sin «Copiar contraseña» ni acciones), Chat con sus propias conversaciones (solo con herramientas de consulta: hora, servicios, bloqueador, dispositivos VPN, sistema y Netflix) y, en Ajustes, su contraseña y la voz. También tiene **Finanzas** (solo sus datos) y los agentes Finanzas y Redes del chat (Redes solo de consulta); Red, Seguridad y Control son de administrador.

Los permisos se aplican **en el servidor** en cada petición, no solo ocultando botones. Cada usuario ve únicamente sus conversaciones, y ARIA le trata por su nombre.

Para invitar a alguien: **Ajustes → Usuarios → Invitar usuario** (email, nombre y rol). Después, autoriza también su email en Cloudflare Access (*Zero Trust → Access → Applications → ARIA → Policies*) para que pueda entrar desde fuera; ARIA no toca Cloudflare. Desde casa puede entrar con la contraseña que le pongas con «Poner contraseña para casa». Desde Usuarios también se cambia el rol, se activa o desactiva (sus sesiones se cierran al instante) y se elimina (con sus conversaciones). Nunca se puede quitar ni degradar al último administrador activo ni a los de `ARIA_ADMIN_EMAILS`.

Al actualizar desde la versión de un solo usuario, ARIA hace una copia en `data/aria.db.bak-sso`, crea el administrador `admin` con la contraseña de siempre y le asigna todas las conversaciones existentes.

## Agentes especializados

Además de ARIA (general), el chat tiene tres «cerebros con oficio». Cada uno tiene su propio prompt en español, sus herramientas y los roles que pueden usarlo; la respuesta lleva la insignia del agente junto a la del cerebro.

| Agente | Para qué | Quién |
|---|---|---|
| **ARIA** | Charla y todo lo de antes (bloqueador, VPN, sistema, Spotify…). Deriva a los especialistas | Todos |
| **Finanzas** | Gastos, ingresos, categorías y presupuestos mensuales. Cada usuario solo ve **sus** datos | Todos |
| **Redes** | Dispositivos de la LAN, latencia, test de velocidad, DNS y VPN | Admin (un usuario solo consulta la salud de la red: latencia, DNS, VPN y la última velocidad) |
| **Seguridad** | Informe defensivo de la red de casa (escaneo de puertos, servicios de riesgo, CVE…) | Solo admin |

**Cómo elegir agente**
- Selector de la cabecera del chat: se guarda en la conversación.
- Prefijo en el mensaje: `@finanzas ¿cuánto llevo gastado?`, `@redes`, `@seguridad`, `@aria` (solo para ese mensaje).
- Con «ARIA (automático)», ARIA enruta sola: primero un filtro de palabras clave (gratis) y, solo si dos agentes empatan, una clasificación de una línea con el primer cerebro en la nube. A un usuario nunca se le enruta a Seguridad, y si escribe `@seguridad` le responde ARIA con un aviso.
- Con el cerebro local de respaldo se mantiene el filtro de herramientas por palabras clave.

### Finanzas: importar el CSV del banco

ARIA **no** se conecta a ningún banco ni usa APIs financieras: los datos llegan a mano, por el chat («apunta 12,50 € en Mercadona») o importando un extracto.

1. En la web de tu banco, descarga los movimientos en **CSV** (si solo da Excel, ábrelo y «Guardar como → CSV»).
2. **Finanzas → Importar extracto CSV** → elige el archivo (máximo 2 MB). Opcionalmente escribe el nombre de la cuenta.
3. ARIA detecta el separador (`;`, `,` o tabulador), la codificación (UTF-8 o latin-1), las líneas de cabecera del banco, la coma o el punto decimal y las fechas (`dd/mm/aaaa`, `dd/mm/aa`, `aaaa-mm-dd`). Revisa el **mapeo de columnas** (Fecha, Concepto, Importe o Debe/Haber, Cuenta) y la vista previa; si cambias una columna, la vista previa se actualiza.
4. Pulsa **Importar**. Los movimientos que ya estaban (misma fecha, importe y concepto) no se duplican, así que puedes reimportar un extracto que se solapa con otro.

Las categorías se asignan con reglas (Mercadona → Supermercado, Repsol → Transporte, Netflix → Suscripciones…). Al editar un movimiento puedes marcar «aplicar a movimientos parecidos» y se crea una regla tuya. El botón **Sugerir categorías (nube)** es opcional: envía solo los **conceptos** sin categoría (sin importes ni fechas) al primer cerebro en la nube y nada se aplica hasta que aceptas cada sugerencia. ARIA no da asesoramiento de inversión.

### Red

**Red** une la tabla de red de Pi-hole (`/api/network/devices`: nombres e IP y última consulta DNS) con el último escaneo (MAC, fabricante y puertos; Pi-hole corre en Docker y no ve las MAC de la LAN). Lo que no está marcado como conocido aparece resaltado; puedes ponerle un alias. La latencia se mide con ping (ICMP sin privilegios) al router, 1.1.1.1 y 8.8.8.8. El **test de velocidad** descarga ~15 MB y sube ~5 MB contra `speed.cloudflare.com` (sin programas de terceros) y se permite uno cada 10 minutos. Las mediciones se guardan 90 días y se dibujan en una gráfica SVG propia.

### Control parental (por dispositivo)

En **Red**, el botón «Control» de cada dispositivo (los nombres vienen del alias que le pongas) permite:

- **Pausar internet** 30 min, 1 h, 2 h, 4 h o hasta reanudar; la tabla muestra «Pausado hasta 20:30».
- **Bloquear servicios**: TikTok, YouTube, Instagram, Facebook, WhatsApp, Snapchat, X, Twitch, Discord, Fortnite/Epic, Roblox, Minecraft, Steam, Netflix, Disney+ y Prime Video (listas de dominios curadas en `control.py`).
- **Horarios**: «sin internet de 23:00 a 08:00 de lunes a viernes» o «sin TikTok de 16:00 a 20:00». Los días son los de inicio del tramo; si «hasta» es menor que «desde» cruza la medianoche. Al empezar o terminar un horario llega un aviso (tipo «Control parental», activo por defecto; se puede desactivar en Ajustes → Avisos).

También desde el agente **@redes** («pausa el iPad una hora», «bloquea TikTok en el móvil», «¿qué dispositivos están pausados?») y desde Telegram con **/control** (lista lo pausado o bloqueado con botones «Reanudar»). Todo es solo de administrador y siempre sobre **un** dispositivo del inventario: no existe una acción «para todos» y el router, la Raspberry (192.168.1.50) y las IP de `ARIA_CONTROL_PROTEGIDOS` no se pueden pausar.

**Cómo funciona.** Usa grupos de SHIELD-DNS (Pi-hole v6): `ARIA-pausa` (regla de denegación regex `.*`) y `ARIA-svc-<servicio>` (regex con los dominios del servicio). ARIA añade la IP del dispositivo como cliente de Pi-hole (siempre también en `Default`, así conserva el bloqueo de anuncios) con el comentario `ARIA-control:<clave>`. Cada 30 s recalcula qué debe estar aplicado (pausas vigentes, horarios activos, servicios) y deja Pi-hole igual; es idempotente, sobrevive a reinicios y, si la IP del dispositivo cambia, mueve el cliente. Solo toca lo que ARIA creó: nunca clientes, grupos ni listas ajenos. Si SHIELD-DNS no responde, lo pedido queda guardado y se aplica en cuanto vuelva.

**Limitación (importante).** Es **solo bloqueo por DNS**. No frena a un dispositivo con DNS fijo (p. ej. 8.8.8.8), con DNS cifrado (DoH/DoT, «DNS privado» de Android, iCloud Relay) o con VPN, ni a los que usan el **DNS secundario del router (AdGuard 94.140.14.14)**. Además, la caché DNS del dispositivo puede tardar unos minutos en notar el cambio. Para un corte total hay que bloquear el dispositivo en el router. La interfaz y el agente lo repiten.

### Seguridad: qué hace y qué no hace el escaneo

El escaneo lo hace un contenedor aparte, **`aria-escaner`** (alpine + nmap): `network_mode: host` (es el único que lo usa; nmap necesita ver la LAN), solo la capacidad `NET_RAW`, sistema de archivos de solo lectura, `no-new-privileges`, sin puertos publicados y sin socket de Docker. La app y el escáner solo se hablan por un volumen compartido (`escaner`): la app deja una petición JSON y el escáner deja el resultado.

**Hace**
- Descubrir equipos y puertos TCP abiertos con versiones de servicio (`nmap -sS -sV`): perfil rápido (100 puertos más comunes) o completo (1000). En el router mira también UPnP (1900/udp) y NAT-PMP (5351/udp).
- Solo en la red de `ARIA_RED_PERMITIDA` (por defecto `192.168.0.0/24`). La app **y** el escáner rechazan cualquier otra cosa: IPs públicas, otras redes privadas, nombres de host, IPv6 y opciones de nmap.
- Un escaneo bajo demanda cada 10 minutos como mucho y uno automático cada domingo a las 04:00.
- Informe con gravedad (alta, media, baja): servicios de riesgo (Telnet, SMB, RDP, VNC, UPnP, bases de datos, API de Docker), paneles de administración web sin HTTPS, puertos nuevos respecto al escaneo anterior, dispositivos sin reconocer, versiones con vulnerabilidades conocidas (OSV.dev para paquetes Debian y NVD para el resto, APIs públicas sin clave; solo se envían nombre de producto y versión, y se guarda en caché 7 días), peers de WireGuard activos y nunca usados, y lo más bloqueado por Pi-hole en cada dispositivo.

**No hace**
- No ataca, no explota vulnerabilidades, no prueba contraseñas y no ejecuta scripts NSE.
- No comprueba la exposición de tu IP pública desde Internet: haría falta un servicio externo que la escanee y no hay ninguno gratuito que sea claramente adecuado. Revisa en el router que solo esté redirigido UDP 51820 (VPN) y que la gestión remota esté desactivada.
- Las coincidencias de NVD son por número de versión: pueden referirse a otras partes del producto y no al servicio expuesto; los avisos de Debian sin puntuación suelen ser menores o estar mitigados.
- Escanear la propia Raspberry desde ella misma no muestra los puertos publicados por Docker (80, 443, 53…), solo los del sistema.

## Actualizar

```bash
./update.sh
```

Hace `git pull --ff-only`, `docker compose pull`, reconstruye con `docker compose up -d --build --remove-orphans`, limpia imágenes y espera a que los tres contenedores estén sanos.

## Copia de seguridad y restauración

```bash
./backup.sh     # crea backups/aria-AAAAMMDD-HHMM.tar.gz (permisos 600) y conserva las 7 más recientes
```

Incluye `.env` y `data/` (conversaciones, modelo activo, contraseña cambiada, token de Spotify). **No** incluye los modelos de Ollama (se vuelven a descargar). Contiene secretos: guárdala fuera de la Pi.

Restaurar en una instalación limpia:

```bash
git clone https://github.com/BertMarti/ARIA.git && cd ARIA
tar -xzf /ruta/aria-AAAAMMDD-HHMM.tar.gz     # recupera .env y data/
./install.sh                                  # conserva el .env restaurado y descarga el modelo
```

Si la restauración es sobre una instalación existente, ejecuta antes `docker compose down` y después `docker compose up -d`.

## Copias de seguridad fuera de la Pi (cifradas)

`./sistema/instalar-copias.sh` activa una copia **diaria a las 04:30**: ejecuta el `backup.sh` de ARIA, HEIMDALL y SHIELD-DNS, añade `~/homelab/cloudflare.env`, lo **cifra con AES-256** y lo sube al repositorio **privado** `TU-USUARIO/homelab-copias` (se guardan las 14 últimas). La contraseña está en `~/homelab/.clave-copias`: **guárdala también fuera de la Pi** (gestor de contraseñas). Sin ella las copias no se pueden abrir.

Registro: `journalctl -t homelab-copias`. Copia manual: `./sistema/copia-diaria.sh`.

**Restaurar tras perder la Raspberry:**
```bash
gh auth login
gh repo clone TU-USUARIO/homelab-copias copias && cd copias
gpg -d homelab-AAAAMMDD-HHMM.tar.gz.gpg | tar -xzf -     # pide la contraseña
# Reinstala todo y restaura cada app con su copia:
curl -fsSL https://raw.githubusercontent.com/BertMarti/ARIA/main/instalar-todo.sh | bash
cp homelab/cloudflare.env ~/homelab/
for p in SHIELD-DNS HEIMDALL ARIA; do mkdir -p ~/homelab/$p/backups; done
cp homelab/shield-dns-*.tar.gz ~/homelab/SHIELD-DNS/backups/ && (cd ~/homelab/SHIELD-DNS && ./restore.sh backups/shield-dns-*.tar.gz)
cp homelab/heimdall-*.tar.gz  ~/homelab/HEIMDALL/backups/  && (cd ~/homelab/HEIMDALL  && ./restore.sh backups/heimdall-*.tar.gz)
cp homelab/aria-*.tar.gz      ~/homelab/ARIA/backups/
```
Para ARIA, extrae su copia en `~/homelab/ARIA` (`tar -xzf backups/aria-*.tar.gz`) y ejecuta `./install.sh`; después `./cloudflare/configurar.sh`.

## Desinstalar

```bash
./uninstall.sh          # elimina contenedores; conserva modelos, certificados y data/
./uninstall.sh --purge  # lo borra todo (pide confirmación)
```

## Pruebas

```bash
docker run --rm -v "$PWD/app:/srv" -w /srv python:3.12-slim sh -c "pip install -q -r requirements.txt pytest && python -m pytest -q"
node app/tests/md.test.js
```

## Puertos

| Proyecto | Puertos |
|---|---|
| ARIA | 80 (redirige a 443), 443 (`aria-escaner` no publica nada) |
| SHIELD-DNS | 53, 8080, 8443 |
| HEIMDALL | 51820/udp, 51843 |

Ollama, SearXNG, la app y `aria-voz` no se publican en el host: solo Caddy es accesible desde la red. `aria-voz` está además en una red interna de Docker sin salida a Internet a la que solo llega la app.

## Solución de problemas

- **No carga la página**: `docker compose ps` y `docker compose logs caddy app`. Comprueba que nada más use los puertos 80/443.
- **Error de certificado al entrar por un nombre**: añade ese nombre a `ARIA_HOSTS` en `.env` y ejecuta `docker compose up -d`.
- **"El modelo no está instalado"**: descárgalo en Ajustes → Modelos o con `docker compose exec ollama ollama pull <modelo>`.
- **Respuestas lentas**: usa un modelo más pequeño o baja `ARIA_NUM_CTX`. La primera respuesta tras un rato tarda más porque el modelo se carga en RAM.
- **Demasiados intentos de login**: 5 fallos bloquean la IP durante 5 minutos.
- **Spotify "no hay dispositivo activo"**: abre Spotify en algún dispositivo y reproduce algo un instante.
- **Aviso "memory limit capabilities"** al arrancar: el kernel de la Pi no tiene activado el cgroup de memoria, así que `mem_limit` se ignora (no afecta al funcionamiento).

## Licencia

MIT. Consulta [LICENSE](LICENSE).
