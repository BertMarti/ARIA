# MEMORY.md

## Decisiones
- **Ollama local**: sin coste ni nube. Modelo por defecto `llama3.2:3b` (cabe en 8 GB y soporta herramientas).
- **FastAPI sin build de frontend**: HTML/CSS/JS plano, mínimas dependencias (fastapi, uvicorn, httpx, itsdangerous, tzdata).
- **Caddy con `tls internal` + `on_demand`**: los navegadores no envían SNI al entrar por IP; se usa `default_sni` con la IP LAN y un endpoint `ask` (`/internal/tls-ask`) que solo autoriza los hosts de `ARIA_HOSTS`. Verificado con `curl -k` por IP y por `.local`; un host no listado es rechazado.
- **Sesión**: cookie firmada (itsdangerous), HttpOnly, Secure, SameSite=Lax; comparación en tiempo constante; 5 fallos/5 min por IP bloquean (en memoria). CSRF: comprobación de `Origin` en POST.
- **DNS check con UDP crudo** (sin dnspython) para no añadir dependencias.
- **Spotify Authorization Code** con token en `data/` (permisos 0600). Netflix: solo enlaces de búsqueda (no hay API).
- `ollama` y `app` no se publican; solo Caddy expone 80/443.

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
- Spotify requiere Premium y un dispositivo activo; el flujo OAuth completo no se ha podido probar sin credenciales reales (sí la ruta "no configurado").
- El modelo 3B usaba herramientas sin motivo (consultaba la hora al saludar o Spotify al pedir un chiste) y a veces escribía la llamada como JSON mal formado en el texto. Solución aplicada: `tools.relevantes()` solo ofrece las herramientas cuyas palabras clave aparecen en el mensaje (`_INTENCIONES`) y `tools.rescatar_llamada()` convierte ese JSON en una llamada real. Tras el cambio, 12 de 12 pruebas correctas (saludos, chiste, explicación, hora, estado, Netflix, Spotify).
- El modelo 3B inventa datos cuando se le pide conocimiento concreto (p. ej. recomendó una película de Netflix inexistente). Es una limitación del tamaño del modelo.
- `mem_limit` se ignora en esta Pi (kernel sin cgroup de memoria).
- Latencia: la primera respuesta tras cargar el modelo tardó ~57 s.
- Limitador de login solo en memoria (las conversaciones sí se guardan en SQLite).
- El modelo 3B resume mal a veces el resultado de las herramientas (p. ej. confundió «disco ocupado» con «libre»; los textos de las herramientas se han hecho más explícitos) y responde de forma torpe tras crear/desactivar dispositivos VPN, aunque la acción se ejecuta bien.
- Los botones «Copiar contraseña» exponen las claves de Pi-hole y wg-easy a cualquier sesión de ARIA.
- RAM observada (Pi de 8 GB con escritorio y otros contenedores): con el modelo cargado, ~5,8 GiB usados y ~2,1 GiB disponibles (antes de cargar: ~3,5 GiB usados).

## Registro de cambios
- **2026-10-07 · v2.0.0**: ARIA pasa a ser el centro de control del laboratorio: Inicio con lanzador, Centro de control (SHIELD-DNS, HEIMDALL, Sistema, Spotify), nuevas herramientas (bloqueador, VPN, sistema, gestión de dispositivos), conversaciones persistentes, selector de modelos, voz opcional, cambio de contraseña, manifest/icono, `update.sh` y `backup.sh`, pruebas pytest y corrección CSRF con `Origin: null`. RAM observada con la v2 en marcha (Pi de 8 GB, modelo descargado de memoria): ~2,9 GiB usados y ~5,0 GiB disponibles; `aria-app` ~41 MiB de RSS.
- **2026-10-06**: selección de herramientas por intención, rescate de llamadas en JSON, textos con tildes, mensaje de Spotify que no pide claves por el chat.
- **2026-10-06**: reescritura completa. Docker Compose (ollama, app, caddy), login, chat con streaming y bucle de herramientas, panel de servicios, Spotify, instalador/desinstalador, documentación en español.
