<p align="center">
  <sub>Parte del ecosistema ARIA&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/ARIA">🤖 ARIA</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/SHIELD-DNS">🛡️ SHIELD-DNS</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/HEIMDALL">🔐 HEIMDALL</a></sub>
  <br>
  <a href="../README.md">🏠 README</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="INSTALACION.md">📘 Instalación</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="USO.md">🧭 Uso</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="MODULOS.md">🧩 Módulos</a>&nbsp;&nbsp;·&nbsp;&nbsp;<b>🗺️ Hoja de ruta</b>
</p>

# Plan de futuro de ARIA

Ideas de nuevas aplicaciones y funciones para ARIA. **Nada de esto está hecho todavía**: es una hoja de ruta para elegir qué viene después.

Todas siguen las mismas reglas que el resto del proyecto:
- **Gratis y autoalojado.** Si hace falta la nube, solo con capas gratuitas y siempre con un respaldo local.
- **Pensado para una Raspberry Pi 5 de 8 GB.**
- **Mismo control de permisos que el resto de ARIA**, siempre en el servidor.

La mayoría se pueden hacer como **módulos** (ver [MODULOS.md](MODULOS.md)), sin tocar el núcleo de ARIA. Cada idea indica dónde encaja:

- **Módulo:** una carpeta en `modulos/` con un manifiesto y, si hace falta, un `modulo.py`.
- **Módulo + contenedor:** el módulo habla con una aplicación que corre en su propio contenedor Docker.
- **Núcleo:** cambia el funcionamiento general de ARIA (chat, voz, avisos…).

Cómo leer las tablas:
- **Esfuerzo:** S = una tarde · M = uno o dos días · L = una semana o más.
- **RAM:** consumo aproximado en la Pi de lo que haya que añadir.

---

## 1. Aplicaciones para conectar (módulos)

### 1.1 Casa y domótica

| Idea | Qué haría ARIA | Tipo | Esfuerzo | RAM |
|---|---|---|---|---|
| **Home Assistant** | Encender y apagar luces o enchufes, consultar sensores, lanzar escenas con la voz («Aria, apaga el salón») | Módulo + contenedor | M | ~300 MB |
| **Govee / Tapo / TP-Link** (sin Home Assistant) | Control directo de las luces Govee y los enchufes Tapo de casa mediante sus APIs locales o de nube | Módulo | M | — |
| **Robot aspirador (Roborock)** | «Aria, aspira la cocina», estado y aviso al terminar (a través de Home Assistant o de la API local) | Módulo | M | — |
| **Impresora 3D (Anycubic / OctoPrint)** | Progreso de la impresión, aviso al terminar o si falla, foto de la cámara | Módulo + contenedor | M | ~150 MB |
| **Cámaras (Frigate)** | Detección de personas o coches en local y aviso por Telegram con la foto | Módulo + contenedor | L | 1 GB o más (mejor con un acelerador Coral) |
| **Consumo eléctrico** | Precio de la luz por horas (PVPC de REE) y aviso de las horas baratas para poner la lavadora | Módulo | S | — |

### 1.2 Multimedia

| Idea | Qué haría ARIA | Tipo | Esfuerzo | RAM |
|---|---|---|---|---|
| **Spotify** (aparcado) | Ya está escrito; se reactiva con `ARIA_SPOTIFY=1` (necesita cuenta Premium) | Ya existe | S | — |
| **Jellyfin** | Biblioteca de películas y series propia; «¿qué película vemos?» con recomendaciones | Módulo + contenedor | M | ~400 MB |
| **Navidrome** | Música propia en streaming, controlable por voz | Módulo + contenedor | M | ~100 MB |
| **Audiobookshelf** | Audiolibros y podcasts | Módulo + contenedor | S | ~150 MB |
| **Fire TV / Android TV** | Encender la tele y abrir apps (ADB en la red local) | Módulo | M | — |

### 1.3 Productividad y documentos

| Idea | Qué haría ARIA | Tipo | Esfuerzo | RAM |
|---|---|---|---|---|
| **Calendario (Radicale, CalDAV)** | Citas por voz, recordatorios desde el calendario y agenda en el resumen de buenos días | Módulo + contenedor | M | ~50 MB |
| **Paperless-ngx** | Documentos escaneados con búsqueda: «¿cuándo caduca el seguro del coche?» | Módulo + contenedor | L | ~700 MB |
| **Nextcloud / archivos** | Buscar y resumir documentos propios | Módulo + contenedor | L | ~500 MB |
| **Correo (IMAP, solo lectura)** | Resumen de correos importantes en el resumen de buenos días | Módulo | M | — |
| **Notas y listas de la compra** | Listas compartidas en la familia («añade leche a la compra») | Módulo | S | — |
| **Vaultwarden** | Gestor de contraseñas propio. ARIA solo mostraría su estado: **nunca leería contraseñas** | Módulo + contenedor | S | ~50 MB |

### 1.4 Red y seguridad

| Idea | Qué haría ARIA | Tipo | Esfuerzo | RAM |
|---|---|---|---|---|
| **Uptime Kuma** | Panel de disponibilidad de webs y servicios, con avisos | Módulo + contenedor | S | ~150 MB |
| **CrowdSec** | Bloqueo colaborativo de IPs atacantes ante el túnel y la VPN | Módulo + contenedor | M | ~150 MB |
| **Router TP-Link** | Lista de clientes con nombre real, reinicio programado del mesh (si la API lo permite) | Módulo | M | — |
| **Copias de seguridad** | Estado de las copias diarias, restaurar un archivo concreto, aviso si una copia falla | Núcleo / módulo | S | — |
| **Speedtest histórico** | Gráfica de velocidad de internet por días, para reclamar a la operadora | Módulo | S | ~50 MB |

### 1.5 Finanzas y vida diaria

| Idea | Qué haría ARIA | Tipo | Esfuerzo | RAM |
|---|---|---|---|---|
| **Bancos (PSD2: GoCardless Bank Account Data)** | Importar movimientos automáticamente, sin subir CSV | Módulo | L | — |
| **Precios y ofertas** | Vigilar el precio de un producto y avisar cuando baje | Módulo (usa Rutinas) | S | — |
| **Gasolineras** | Gasolinera más barata cerca de casa (datos abiertos del Ministerio) | Módulo | S | — |
| **Tráfico y transporte** | Incidencias de la DGT en tu ruta; horarios de autobús | Módulo | M | — |
| **Salud** | Recordatorios de medicación con confirmación por Telegram | Módulo | S | — |

---

## 2. Mejoras del propio ARIA (núcleo)

| Idea | Para qué | Esfuerzo |
|---|---|---|
| **Documentos propios (RAG)** | Subir PDFs o notas y preguntar sobre ellos, usando embeddings gratuitos o en local | L |
| **Voz sin internet de calidad** | Voz más natural en local cuando la Pi tenga margen (modelos TTS pequeños optimizados para ARM) | M |
| **Altavoz satélite** | Una Raspberry Pi Zero o un ESP32 con micrófono en otra habitación que despierte con «Aria» | L |
| **Modo familia** | Perfiles infantiles con control parental propio y respuestas adaptadas | M |
| **Panel personalizable** | Elegir y ordenar las tarjetas de Inicio, incluidas las de los módulos | M |
| **Historial de la red** | Gráficas por dispositivo: consultas, bloqueos y horas de uso | M |
| **Agentes a medida** | Crear agentes nuevos desde Ajustes (nombre, instrucciones y herramientas) sin programar | M |
| **Catálogo de módulos** | Instalar módulos de la comunidad desde un repositorio, con firma y revisión | L |
| **App de escritorio** | Atajo global en Windows para hablar con ARIA (a partir de la web instalable) | M |
| **WhatsApp** | Igual que Telegram. Se descartó porque la API oficial es de pago y las no oficiales arriesgan la cuenta | — |

---

## 3. Orden propuesto

Ordenado por lo que más aporta con menos esfuerzo y menos consumo en la Pi:

1. **Precio de la luz (PVPC)**, **gasolineras** y **vigilar precios**: pequeños, útiles cada día y encajan con las rutinas.
2. **Calendario (Radicale)**: completa el resumen de buenos días y los recordatorios.
3. **Home Assistant**: abre la puerta a las luces, los enchufes y el robot de casa con un solo módulo.
4. **Uptime Kuma** e **historial de velocidad**: mejor vigilancia de la casa con poco consumo.
5. **Documentos propios (RAG)** y **Paperless-ngx**: el gran salto como asistente personal, pero el más pesado.
6. **Altavoz satélite**: «Aria» en toda la casa.

Antes de añadir contenedores pesados (Frigate, Paperless, Jellyfin), mira la RAM libre en ARIA → Centro de control → Sistema. ARIA, Ollama y la voz ya usan la mayor parte de los 8 GB.
