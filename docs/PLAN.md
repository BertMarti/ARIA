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
| **Consumo eléctrico** | ✅ Hecho: precio de la luz por horas (PVPC de REE). Pendiente: aviso automático de las horas baratas | Núcleo | S | — |

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
| **Calendario (Radicale, CalDAV)** | La agenda propia y la suscripción iCalendar ya están hechas; CalDAV añadiría editar desde el móvil | Módulo + contenedor | M | ~50 MB |
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

## Hecho en octubre de 2026

Ya disponible (ver la [guía de uso](USO.md)):
- **Modo HUD:** pantalla completa con un orbe animado que reacciona a la voz y widgets.
- **Agenda y cumpleaños:** con avisos y resumen de buenos días.
- **Mapas libres:** OpenStreetMap, rutas y sitios cercanos, sin claves.
- **Centro de información:** noticias por temas con resumen, bolsa y criptomonedas.
- **Estadísticas por dispositivo** e **informe semanal** de la red y la VPN.
- **Resumen diario** en Inicio, HUD y Telegram (con botones); **sistema en directo**, **reinicio seguro** y **automatizaciones**.
- **HUD futurista** con tarjetas interactivas, opciones y modo quiosco; **precio de la luz** (PVPC); **agenda en el móvil** (iCalendar); **verificación en dos pasos**; gráficas de cripto; Ajustes por secciones.

## ARIA PRO (en marcha)

Aprobado y en curso. La idea es enseñar ARIA mejor y darle funciones de asistente «de película», sin perder lo que es: una IA de casa, cálida y que no hace nada sin permiso.

| Bloque | Qué | Estado |
|---|---|---|
| **Escaparate público** | Página «Conoce a ARIA»: portada oscura con su voz presentándose (pregrabada), menú en tarjetas numeradas y demos de solo lectura con datos inventados. Sin IA en vivo, sin formularios ni analítica y **Ping**, su hada de luz con voz propia, en `/hola` | ✅ Hecho |
| **Inicio en tarjetas** | El menú principal de ARIA como tarjetas numeradas con estado (activo, aviso, pronto) | ✅ Hecho |
| **Voz «Elegante»** | Nuevo tono: serena, segura, con un punto de ironía amable | ✅ Hecho |
| **Voz diseñada** | Una voz nueva creada a partir de una descripción (Qwen3-TTS VoiceDesign, Apache 2.0) y entrenada para Piper con [herramientas/voz-propia](../herramientas/voz-propia/README.md): local y sin cuotas | Propuesta |
| **Voz en streaming** | Empezar a hablar al terminar la primera frase | Propuesta |
| **Memoria de verdad** | Búsqueda semántica local, recuerdos con fuente y confianza, olvido de lo que no se usa | Propuesta |
| **Proactividad con permiso** | ARIA propone acciones ante eventos en una bandeja (aprobar o rechazar) y registra todo lo que hace | Propuesta |
| **Briefing hablado** | Un minuto de voz cada mañana con lo importante (Telegram como nota de voz, HUD e Inicio) | ✅ Hecho |
| **Ojos y gestos en el HUD** | Cámara bajo petición («¿qué ves?») y control con la mano (MediaPipe, en el navegador) | Propuesta |
| **Mapa 3D** | MapLibre + OpenFreeMap: edificios en 3D y «vuela a…», sin claves | Propuesta |
| **ARIA flotante** | Mini-ventana siempre visible en el PC con orbe, subtítulos y micrófono | Propuesta |

Fuera de alcance a propósito: reconocimiento facial y rastreo de información sobre personas.

## 3. Orden propuesto

Ordenado por lo que más aporta con menos esfuerzo y menos consumo en la Pi:

1. **Gasolineras** y **vigilar precios** (la luz ya está hecha): pequeños, útiles cada día y encajan con las rutinas.
2. **Calendario bidireccional (CalDAV)**: editar la agenda desde el móvil (ya se puede ver con la suscripción).
3. **Home Assistant**: abre la puerta a las luces, los enchufes y el robot de casa con un solo módulo.
4. **Uptime Kuma** e **historial de velocidad**: mejor vigilancia de la casa con poco consumo.
5. **Documentos propios (RAG)** y **Paperless-ngx**: el gran salto como asistente personal, pero el más pesado.
6. **Altavoz satélite**: «Aria» en toda la casa.

Antes de añadir contenedores pesados (Frigate, Paperless, Jellyfin), mira la RAM libre en ARIA → Centro de control → Sistema. ARIA, Ollama y la voz ya usan la mayor parte de los 8 GB.
