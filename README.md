# ARIA

Asistente doméstico local estilo "Jarvis" para Raspberry Pi. El modelo de lenguaje se ejecuta en tu propia máquina con [Ollama](https://ollama.com): **sin APIs de pago y sin enviar tus conversaciones a la nube**.

Incluye:

- **Inicio**: saludo, lanzador de aplicaciones con su estado en vivo (Chat, SHIELD-DNS, HEIMDALL, Spotify), acciones rápidas y estado de la Pi.
- **Chat** con conversaciones guardadas, streaming, botón Detener, copiar, Markdown seguro y lectura en voz alta opcional. Herramientas: hora, bloqueador de anuncios, VPN, estado de la Raspberry, Spotify y Netflix (enlaces).
- **Centro de control** para [SHIELD-DNS](https://github.com/BertMarti/SHIELD-DNS) (Pi-hole), [HEIMDALL](https://github.com/BertMarti/HEIMDALL) (VPN WireGuard), el sistema y Spotify.
- **Ajustes**: modelos, voz, cambio de contraseña, Spotify y versión.
- **HTTPS** automático (certificado propio de Caddy), acceso con usuario y contraseña, y se puede añadir a la pantalla de inicio del móvil.

## Guía rápida de uso

1. **Entrar.** Abre `https://<IP-de-la-Pi>`, acepta el aviso del certificado (es lo esperado) e inicia sesión. Para tenerla como app, en el móvil usa «Añadir a pantalla de inicio».
2. **Inicio.** Es la página por defecto. Arriba escribe en «Pregúntale a ARIA» para abrir un chat con esa pregunta. Las cuatro fichas abren cada aplicación en una pestaña nueva (el punto indica si está activa, caída o sin instalar); en SHIELD-DNS y HEIMDALL, «Copiar contraseña» te evita teclearla en su panel. Debajo tienes las acciones rápidas y el estado de la Pi.
3. **Chat.** Escribe en la parte inferior; «Detener» corta la respuesta, «Copiar» copia un mensaje. A la izquierda (☰ en el móvil) están tus conversaciones: «+ Nueva», ✎ renombrar y ✕ borrar. Prueba: «¿Cuántos anuncios has bloqueado hoy?» o «¿Qué temperatura tiene la Raspberry?».
4. **Centro de control.** Tarjetas de SHIELD-DNS, HEIMDALL, Sistema y Spotify; se actualizan solas cada 15 s.
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

Clona los tres repositorios en `~/homelab` y los instala en el orden correcto (SHIELD-DNS, HEIMDALL y ARIA, que detecta a los otros dos y se conecta a ellos). Con `COPIAS_AUTOMATICAS=1` delante programa además una copia de seguridad diaria de las tres apps a las 04:30. La guía completa de las tres apps está en [docs/GUIA.md](docs/GUIA.md).

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
- Tratamiento: ARIA te llama por tu nombre (`ARIA_NOMBRE_USUARIO`, por defecto «Lucía»).

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

`install.sh` las rellena solo si están vacías y existen `../SHIELD-DNS/.env` y `../HEIMDALL/.env` (se leen con `grep`, nunca se ejecutan). Tras editar `.env`: `docker compose up -d`.

Seguridad: las claves privadas de WireGuard nunca llegan al navegador salvo el `.conf` que tú descargas expresamente. **Aviso:** los botones «Copiar contraseña» de Inicio entregan la contraseña de Pi-hole y de wg-easy a cualquier persona que haya iniciado sesión en ARIA (solo mediante una petición autenticada y sin caché; no van en el HTML). Protege bien la contraseña de ARIA.

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
- **Usuario**: Inicio (solo estado, sin «Copiar contraseña» ni acciones), Chat con sus propias conversaciones (solo con herramientas de consulta: hora, servicios, bloqueador, dispositivos VPN, sistema y Netflix) y, en Ajustes, su contraseña y la voz.

Los permisos se aplican **en el servidor** en cada petición, no solo ocultando botones. Cada usuario ve únicamente sus conversaciones, y ARIA le trata por su nombre.

Para invitar a alguien: **Ajustes → Usuarios → Invitar usuario** (email, nombre y rol). Después, autoriza también su email en Cloudflare Access (*Zero Trust → Access → Applications → ARIA → Policies*) para que pueda entrar desde fuera; ARIA no toca Cloudflare. Desde casa puede entrar con la contraseña que le pongas con «Poner contraseña para casa». Desde Usuarios también se cambia el rol, se activa o desactiva (sus sesiones se cierran al instante) y se elimina (con sus conversaciones). Nunca se puede quitar ni degradar al último administrador activo ni a los de `ARIA_ADMIN_EMAILS`.

Al actualizar desde la versión de un solo usuario, ARIA hace una copia en `data/aria.db.bak-sso`, crea el administrador `admin` con la contraseña de siempre y le asigna todas las conversaciones existentes.

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
| ARIA | 80 (redirige a 443), 443 |
| SHIELD-DNS | 53, 8080, 8443 |
| HEIMDALL | 51820/udp, 51843 |

Ollama y la app no se publican en el host: solo Caddy es accesible desde la red.

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
