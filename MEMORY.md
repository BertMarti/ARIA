# MEMORY.md

## Decisiones
- **Ollama local**: sin coste ni nube. Modelo por defecto `llama3.2:3b` (cabe en 8 GB y soporta herramientas).
- **FastAPI sin build de frontend**: HTML/CSS/JS plano, mínimas dependencias (fastapi, uvicorn, httpx, itsdangerous, tzdata).
- **Caddy con `tls internal` + `on_demand`**: los navegadores no envían SNI al entrar por IP; se usa `default_sni` con la IP LAN y un endpoint `ask` (`/internal/tls-ask`) que solo autoriza los hosts de `ARIA_HOSTS`. Verificado con `curl -k` por IP y por `.local`; un host no listado es rechazado.
- **Sesión**: cookie firmada (itsdangerous), HttpOnly, Secure, SameSite=Lax; comparación en tiempo constante; 5 fallos/5 min por IP bloquean (en memoria). CSRF: comprobación de `Origin` en POST.
- **DNS check con UDP crudo** (sin dnspython) para no añadir dependencias.
- **Spotify Authorization Code** con token en `data/` (permisos 0600). Netflix: solo enlaces de búsqueda (no hay API).
- `ollama` y `app` no se publican; solo Caddy expone 80/443.

## Decisiones de la cadena de cerebros (2026-10-07)
- **Cadena Ollama Cloud → Groq → Gemini → local**, todo gratuito. Cada fallo (429/cuota, clave, modelo, timeout, red) pasa al siguiente; la cuota se recuerda 15 min (o `Retry-After`), clave/modelo 30 min, red/timeout 60 s. Esperas solo en memoria; orden y activación en `data/cerebros.json`.
- **Ollama Cloud por defecto `gpt-oss:120b-cloud`**: medido desde `aria-app` con herramientas, 120b dio primer token 0,3-0,4 s (2,0 s con llamada a herramienta una vez) frente a 2,0-3,2 s de 20b; ambos llaman bien a las herramientas. El razonamiento llega en `message.thinking` y se descarta.
- **Gemini por defecto `gemini-3.1-flash-lite`**: `gemini-2.5-flash` (y 2.5-flash-lite) responden 404 «no longer available to new users» aunque aparezcan en el listado; `gemini-flash-latest` tardó 12 s. Los modelos Gemini 3 devuelven `thought_signature` en `extra_content` de cada tool_call y hay que reenviarlo.
- **Groq**: sin clave en esta instalación, no probado en real (solo pruebas unitarias del adaptador OpenAI). Por defecto `openai/gpt-oss-120b`.
- Herramientas: las nubes reciben todas; `relevantes()`/`rescatar_llamada()` solo para el local. Mensajes internos en formato Ollama, convertidos al vuelo.
- Con la nube, los mensajes salen de casa (Google puede usarlos para mejorar productos en el plan gratuito); el local sigue siendo 100 % privado.
- Latencias reales (LAN, 2026-10-07, primer token / total): «Hola» Ollama Cloud 0,5/0,6 s, Gemini 1,0/1,1 s, local 0,8-1,2/4,5-5,3 s; «temperatura de la Raspberry» (con herramienta) Ollama Cloud 0,8/0,9 s, Gemini 3,3/3,4 s, local 20/28-32 s; «anuncios bloqueados» Ollama Cloud 1,1/1,3 s, Gemini 2,3/2,3 s, local 15-26/34-48 s. «Probar»: Ollama Cloud 0,5 s, Gemini 1,0 s, local 2 s (modelo caliente).

## Decisiones de búsqueda en internet (2026-10-07)
- SearXNG propio (`aria-searxng`, imagen oficial arm64) en lugar de una API de pago: sin claves, sin puertos publicados, JSON activado y limitador desactivado (solo interno). `SEARXNG_SECRET` en `.env`.
- Motores: DuckDuckGo y Bing responden desde esta red; Brave y Google devuelven «too many requests»/«access denied» y quedan como respaldo (SearXNG los suspende solos). Bing y Google vienen desactivados por defecto y se activan en `settings.yml`.
- Herramientas de solo lectura para ambos roles. El modelo local las recibe por palabras clave; las nubes siempre, con el prompt pidiendo citar «Fuentes:» y con la fecha actual (si no, buscaban «2024»).
- Se descartan resultados en escrituras no latinas (salían titulares en chino) salvo que la consulta las use.
- RAM medida: SearXNG ~145 MB RSS (worker ~106 MB), límite 384 MB. El cgroup de memoria no está activo en esta Pi, así que `docker stats` marca 0.
- Privacidad: las consultas y el texto de los resultados llegan al cerebro en la nube que responda.

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

## Decisiones de memoria y resumen de buenos días (2026-10-07)
- Memoria por usuario en `data/aria.db` (`recuerdos`, `diario`, `memoria_ajustes`, `resumen_dia`; FK con `ON DELETE CASCADE` a `usuarios`). Copia previa: `data/aria.db.bak-memoria`.
- Extracción automática solo con cerebros de la nube, tras el turno y en una tarea de fondo con semáforo (nunca el local: compite con el chat y es lento). Sin nube = no se aprende. Se salta si el turno usó `recordar`/`olvidar` (si no, «olvida X» se volvería a aprender) y con mensajes < 20 caracteres.
- Filtro de secretos por expresiones regulares (palabras clave, tarjetas, DNI/NIE, IBAN, prefijos de tokens, cadenas largas) además de la instrucción al modelo; también aplica a `recordar` y a lo editado a mano. Falsos positivos aceptados (p. ej. «clave»).
- Tope de 200: se descartan primero los automáticos menos usados y más antiguos; los del usuario nunca se borran solos. Un recuerdo editado pasa a «usuario».
- Presupuesto de prompt: nube ~1 200 + ~900 (3 días); local ≤ 300 (5 recuerdos, sin diario). Se marca `usado` al inyectar.
- Diario: planificador asyncio en la app (03:30 `ARIA_TZ`, recuperación de 14 días al arrancar, sin contenedor nuevo). Los límites del día usan calendario local (DST: 23/25 h). Quien apaga «Aprender automáticamente» tampoco tiene diario (decisión mía: resumir conversaciones también es aprender de ellas).
- Resumen de buenos días: caché por usuario y día; el «hola» del primer día se responde sin llamar a ningún cerebro (plantilla), así que es instantáneo. Datos solo de admin (VPN, copias) se quitan en servidor. La copia fuera de la Pi no está montada en `aria-app`, así que sale «no disponible» (no se monta nada nuevo). Anuncios de ayer vía `/api/stats/database/summary` de Pi-hole (si no hay datos, últimas 24 h).
- Tiempo: Open-Meteo, `ARIA_CIUDAD="Ronda, Málaga"` con `ARIA_LAT`/`ARIA_LON` fijos (sin geocodificar).
- **Privacidad**: los recuerdos y el diario viajan a Ollama Cloud/Groq/Gemini con cada pregunta (Google puede usarlos en el plan gratuito). El local recibe ≤ 300 caracteres. Borrado total desde Ajustes → Memoria.

## Decisiones de los agentes especializados (2026-10-07)
- **Agentes** = prompt + herramientas + roles + cerebro preferido (`agentes.py`). Enrutado automático barato: palabras clave; solo si empatan dos agentes, una línea al primer cerebro en la nube (8 s máx.). El resultado de la nube se vuelve a filtrar por rol. ARIA general ya no ofrece las herramientas de especialista (las pruebas que asumían «todas» se ajustaron).
- **Rol `usuario`**: Finanzas (solo sus datos), lista de agentes y `GET /api/red/salud` + herramienta `estado_red` (latencia, DNS, VPN y última velocidad: inocuo). Dispositivos de la LAN, test de velocidad, latencia bajo demanda y todo Seguridad son de admin (privacidad de quién está en casa y consumo de ancho de banda).
- **Finanzas**: céntimos enteros; deduplicado por (fecha, importe, concepto normalizado) contando repeticiones (k filas iguales en el CSV − j ya guardadas), así no se pierden dos cafés iguales y reimportar no duplica. Desde el chat no se crean categorías nuevas. Sugerencias de la nube solo con conceptos y con aceptación explícita.
- **Pi-hole** (`/api/network/devices` verificado: `hwaddr`, `interface`, `firstSeen`, `lastQuery`, `numQueries`, `macVendor`, `ips[{ip,name,lastSeen,nameUpdated}]`): en esta instalación 20 de 21 «dispositivos» son `ip-x.x.x.x` sin MAC ni fabricante (Pi-hole va en Docker). Las MAC y fabricantes salen del escaneo de nmap (ARP). Bloqueos por cliente: `/api/stats/top_clients?blocked=true` + `/api/queries?client_ip=…&upstream=blocklist`.
- **Velocidad**: `speed.cloudflare.com/__down` responde 403 a más de ~10 MB por petición → 3 trozos de 5 MB + 5 MB de subida. Medido en la Pi: 234 Mbps ↓ / 76 Mbps ↑.
- **Latencia**: ICMP sin privilegios (`SOCK_DGRAM`/`IPPROTO_ICMP`; Docker deja `ping_group_range` abierto); si falla, conexión TCP.
- **Escáner**: contenedor aparte con nmap (alpine), `network_mode: host`, `cap_drop: ALL` + `NET_RAW` (NET_ADMIN no hizo falta), `read_only`, `no-new-privileges`, `user 0:<gid de la app>` y volumen `/escaner` con 2770 y setgid para que ambos lados lean/escriban sin DAC_OVERRIDE. Comunicación solo por archivos JSON. Doble validación de CIDR (app y escáner), argumentos de nmap fijos por perfil y sin shell.
- **CVE**: OSV.dev para banners «Debian …debNNuM» (ecosistema `Debian:NN`, versión con epoch), NVD `virtualMatchString` para el resto (6,5 s entre peticiones, 8 nuevas por informe, caché 7 días). Sin puntuación = gravedad baja. Hallazgos agrupados por equipo y versión.
- **Exposición externa**: no implementada (ningún servicio gratuito claramente adecuado para escanear la IP pública desde fuera); queda como recomendación manual en el informe.
- Primer escaneo real (2026-10-07, 100 puertos, 182 s): 21 equipos, 24 puertos abiertos. Hallazgos: firmware de los nodos TP-Link con BusyBox httpd 1.19.4 y BIND 9.18.29 con CVE en NVD, VNC (5900) abierto en la Pi, paneles web del router/nodos por HTTP, UPnP y NAT-PMP activos en el router y todos los dispositivos aún sin reconocer.

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
- Los botones «Copiar contraseña» exponen las claves de Pi-hole y wg-easy a cualquier administrador de ARIA (los usuarios normales no los ven ni pueden pedirlas).
- RAM observada (Pi de 8 GB con escritorio y otros contenedores): con el modelo cargado, ~5,8 GiB usados y ~2,1 GiB disponibles (antes de cargar: ~3,5 GiB usados).

## Registro de cambios
- **2026-10-07 · agentes especializados**: agentes ARIA/Finanzas/Redes/Seguridad con selector, prefijo `@`, enrutado automático e insignia; Finanzas por usuario con importación CSV de bancos españoles; Red (dispositivos, latencia, velocidad, historial); Seguridad con el contenedor `aria-escaner` (nmap limitado a 192.168.0.0/24) e informe por gravedad con CVE de OSV/NVD. Verificado en un proyecto de prueba aparte (`aria-agentes`, contenedores `agt-*`, ya eliminado): escaneo real de la LAN, dispositivos de Pi-hole, latencia, test de velocidad, CSV sintético (6 importados y 6 duplicados al reimportar), chat con @finanzas, @redes y @seguridad por Ollama Cloud, y un usuario de prueba con 403 en Red/Seguridad y aviso al pedir @seguridad.
- **2026-10-07 · búsqueda en internet**: servicio `aria-searxng`, `busqueda.py`, herramientas `buscar_en_internet` y `noticias`, chip «Buscando en internet…» con enlaces a las fuentes, `SEARXNG_SECRET` en install/update. Verificado con consultas reales (Ronda Jaén, noticias Raspberry Pi, precio luz hoy España) y con un cerebro en la nube que llama a la herramienta y cita fuentes.
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
- **2026-10-07 · memoria y resumen de buenos días**: recuerdos por usuario (`recordar`/`olvidar`, aprendizaje automático en segundo plano), diario nocturno, contexto en el prompt, tarjeta «Tu resumen de hoy», `GET /api/briefing`, `POST /api/diario/generar` (admin) y Ajustes → Memoria. 310 pruebas. Verificado en real: «Recuerda que mi equipo es el Betis» + conversación nueva «¿Cuál es mi equipo?» → «Tu equipo es el Betis»; resumen con cifras reales de Pi-hole/VPN/Pi; diario generado por Ollama Cloud; datos de prueba borrados.
- **2026-10-07**: búsqueda en internet integrada (SearXNG, fusión de feat/busqueda). Herramienta `tiempo` (Open-Meteo, 7 días etiquetados HOY/MAÑANA/FIN DE SEMANA); el prompt incluye el día de la semana y las fechas del fin de semana (gpt-oss calculaba mal el fin de semana). La última ronda del bucle de herramientas va sin herramientas para forzar una respuesta.
