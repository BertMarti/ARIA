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

Abre `https://<IP-de-la-Pi>` (o `https://<nombre-de-la-Pi>.local`) e inicia sesión con `ARIA_USER` / `ARIA_PASSWORD` de `.env`. Después puedes cambiar la contraseña desde **Ajustes** (ver la guía rápida).

### Aviso de certificado

El navegador mostrará "la conexión no es privada". Es normal: ARIA usa la autoridad certificadora interna de Caddy, que tu navegador no conoce. El tráfico va cifrado igualmente. Acepta la excepción (Avanzado → Continuar). Si quieres evitar el aviso, importa el certificado raíz que Caddy genera en el volumen `caddy_data` (`/data/caddy/pki/authorities/local/root.crt` dentro de `aria-caddy`) en tus dispositivos:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./aria-root.crt
```

Los certificados se emiten bajo demanda solo para los nombres/IPs listados en `ARIA_HOSTS` (`.env`). Si accedes con otro nombre, añádelo ahí y reinicia con `docker compose up -d`.

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
