# ARIA

Asistente doméstico local estilo "Jarvis" para Raspberry Pi. El modelo de lenguaje se ejecuta en tu propia máquina con [Ollama](https://ollama.com): **sin APIs de pago y sin enviar tus conversaciones a la nube**.

Incluye:

- **Chat** en el navegador (también en el móvil) con respuestas en streaming y herramientas: hora, estado de servicios, Spotify y búsquedas en Netflix.
- **Panel** con el estado de [SHIELD-DNS](https://github.com/BertMarti/SHIELD-DNS) y [HEIMDALL](https://github.com/BertMarti/HEIMDALL), gestión del modelo y controles de Spotify.
- **HTTPS** automático (certificado propio de Caddy) y acceso protegido por usuario y contraseña.

## Requisitos

- Raspberry Pi 5 (u otra máquina arm64/amd64) con 8 GB de RAM, Raspberry Pi OS o Debian/Ubuntu.
- Docker y `docker compose` v2 (si falta Docker, `install.sh` ofrece instalarlo con el script oficial).
- Unos 3 GB libres de disco para el modelo por defecto, y libres los puertos 80 y 443.

## Instalación

```bash
git clone https://github.com/BertMarti/ARIA.git && cd ARIA && ./install.sh
```

El script es idempotente: puedes relanzarlo sin problema. Hace lo siguiente:

1. Crea `.env` (si no existe) con una contraseña y un secreto aleatorios y detecta la IP de la LAN.
2. Construye y arranca los tres contenedores (`aria-ollama`, `aria-app`, `aria-caddy`).
3. Espera a que estén sanos y descarga el modelo (`ARIA_MODEL`). Con `SKIP_MODEL=1 ./install.sh` se omite la descarga; luego puedes hacerla desde el panel.
4. Muestra la URL y las credenciales.

## Primer acceso

Abre `https://<IP-de-la-Pi>` (o `https://<nombre-de-la-Pi>.local`) e inicia sesión con `ARIA_USER` / `ARIA_PASSWORD` de `.env`. Para cambiar la contraseña edita `.env` y ejecuta `docker compose up -d`.

### Aviso de certificado

El navegador mostrará "la conexión no es privada". Es normal: ARIA usa la autoridad certificadora interna de Caddy, que tu navegador no conoce. El tráfico va cifrado igualmente. Acepta la excepción (Avanzado → Continuar). Si quieres evitar el aviso, importa el certificado raíz que Caddy genera en el volumen `caddy_data` (`/data/caddy/pki/authorities/local/root.crt` dentro de `aria-caddy`) en tus dispositivos:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./aria-root.crt
```

Los certificados se emiten bajo demanda solo para los nombres/IPs listados en `ARIA_HOSTS` (`.env`). Si accedes con otro nombre, añádelo ahí y reinicia con `docker compose up -d`.

## Modelo local

El modelo por defecto es `llama3.2:3b` (unos 2 GB). En una Pi de 8 GB funciona, pero con una velocidad modesta (unos pocos tokens por segundo). Alternativas probadas como existentes en la biblioteca de Ollama: `qwen2.5:3b`, `gemma2:2b` y `llama3.2:1b` (más rápido y más flojo). Para cambiar de modelo:

```bash
# 1. Edita ARIA_MODEL en .env
# 2. Descarga el modelo y recrea la app
docker compose exec ollama ollama pull qwen2.5:3b
docker compose up -d
```

Consejos: los modelos más pequeños responden antes pero fallan más al usar herramientas; con 8 GB evita modelos de 7B o más si la Pi además ejecuta escritorio. `ARIA_NUM_CTX` y `OLLAMA_KEEP_ALIVE` en `.env` controlan la RAM usada. Si el modelo no admite herramientas, ARIA lo detecta y responde sin ellas.

## Herramientas del asistente

| Herramienta | Qué hace |
|---|---|
| `fecha_hora` | Fecha y hora actuales |
| `estado_servicios` | Estado de SHIELD-DNS y HEIMDALL |
| `spotify_play`, `spotify_pause`, `spotify_siguiente`, `spotify_anterior`, `spotify_actual`, `spotify_buscar_y_reproducir` | Control de Spotify |
| `buscar_en_netflix` | Devuelve un enlace de búsqueda en Netflix |

### Limitación con Netflix

Netflix **no tiene API pública**. ARIA no puede controlar su reproducción: solo genera un enlace `netflix.com/search?q=...` que tú abres.

## Spotify (opcional)

El control de reproducción de la Web API de Spotify **requiere una cuenta Premium**.

1. Entra en <https://developer.spotify.com/dashboard> y crea una app.
2. Añade como *Redirect URI* exactamente `https://<IP-de-la-Pi>/spotify/callback` (es el valor por defecto de `SPOTIFY_REDIRECT_URI`; Spotify exige HTTPS salvo para loopback).
3. Copia el *Client ID* y el *Client secret* a `SPOTIFY_CLIENT_ID` y `SPOTIFY_CLIENT_SECRET` en `.env`.
4. `docker compose up -d` y, en el panel de ARIA, pulsa **Conectar Spotify**.
5. Debe haber un dispositivo con Spotify abierto (móvil, ordenador, altavoz) para que haya "dispositivo activo".

El token se guarda en `data/spotify_token.json` (ignorado por git).

## Panel de servicios

- **SHIELD-DNS**: resuelve un nombre contra `SHIELD_DNS_HOST:SHIELD_DNS_PORT` y comprueba el puerto web `SHIELD_WEB_PORT` (8443); enlace a `/admin`.
- **HEIMDALL**: comprueba el puerto TCP `HEIMDALL_PORT` (51843).

Si no responden se muestran como "No instalado o sin respuesta". Los valores se configuran en `.env`.

## Actualizar

```bash
git pull && ./install.sh
```

Para actualizar las imágenes base: `docker compose pull ollama caddy && docker compose up -d --build`.

## Desinstalar

```bash
./uninstall.sh          # elimina contenedores; conserva modelos, certificados y data/
./uninstall.sh --purge  # lo borra todo (pide confirmación)
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
- **"El modelo no está instalado"**: pulsa *Descargar modelo* en el panel o `docker compose exec ollama ollama pull <modelo>`.
- **Respuestas lentas**: usa un modelo más pequeño o baja `ARIA_NUM_CTX`. La primera respuesta tras un rato tarda más porque el modelo se carga en RAM.
- **Demasiados intentos de login**: 5 fallos bloquean la IP durante 5 minutos.
- **Spotify "no hay dispositivo activo"**: abre Spotify en algún dispositivo y reproduce algo un instante.
- **Aviso "memory limit capabilities"** al arrancar: el kernel de la Pi no tiene activado el cgroup de memoria, así que `mem_limit` se ignora (no afecta al funcionamiento).

## Licencia

MIT. Consulta [LICENSE](LICENSE).
