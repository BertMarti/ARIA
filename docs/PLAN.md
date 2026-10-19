<p align="center">
  <sub>Parte del ecosistema ARIA&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/ARIA">🤖 ARIA</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/SHIELD-DNS">🛡️ SHIELD-DNS</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/HEIMDALL">🔐 HEIMDALL</a></sub>
  <br>
  <a href="../README.md">🏠 README</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="INSTALACION.md">📘 Instalación</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="USO.md">🧭 Uso</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="MODULOS.md">🧩 Módulos</a>&nbsp;&nbsp;·&nbsp;&nbsp;<b>🗺️ Hoja de ruta</b>
</p>

# Plan de futuro de ARIA

Ideas de nuevas aplicaciones y funciones para ARIA. Las filas marcadas como hechas describen lo que ya está disponible hoy.

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
| **Govee / Tapo / TP-Link** (sin Home Assistant) | ✅ Hecho en parte: controla luces Govee, cámaras Tapo y algunas funciones del router TP-Link desde Hogar | Núcleo | M | — |
| **Robot aspirador (Roborock)** | «Aria, aspira la cocina», estado y aviso al terminar (a través de Home Assistant o de la API local) | Módulo | M | — |
| **Impresora 3D (Anycubic / OctoPrint)** | Progreso de la impresión, aviso al terminar o si falla, foto de la cámara | Módulo + contenedor | M | ~150 MB |
| **Cámaras (Frigate)** | ✅ Hecho, sin Frigate: cámaras Tapo con detección, vigilancia cuando no hay nadie, eventos con foto y avisos | Núcleo | L | — |
| **Consumo eléctrico** | ✅ Hecho: precio de la luz por horas (PVPC de REE), aviso de las horas baratas de mañana cada tarde y al empezar la de hoy | Núcleo | S | — |

### 1.2 Multimedia

| Idea | Qué haría ARIA | Tipo | Esfuerzo | RAM |
|---|---|---|---|---|
| **Spotify** (aparcado) | ✅ Hecho pero aparcado: se reactiva con `ARIA_SPOTIFY=1` (necesita cuenta Premium) | Ya existe | S | — |
| **Jellyfin** | Biblioteca de películas y series propia; «¿qué película vemos?» con recomendaciones | Módulo + contenedor | M | ~400 MB |
| **Navidrome** | Música propia en streaming, controlable por voz | Módulo + contenedor | M | ~100 MB |
| **Audiobookshelf** | Audiolibros y podcasts | Módulo + contenedor | S | ~150 MB |
| **Fire TV / Android TV** | Encender la tele y abrir apps (ADB en la red local) | Módulo | M | — |

### 1.3 Productividad y documentos

| Idea | Qué haría ARIA | Tipo | Esfuerzo | RAM |
|---|---|---|---|---|
| **Calendario (Radicale, CalDAV)** | ✅ Hecho en parte: agenda propia, suscripción iCalendar y descarga `.ics`; falta editar desde el móvil por CalDAV | Núcleo | M | — |
| **Paperless-ngx** | Documentos escaneados con búsqueda: «¿cuándo caduca el seguro del coche?» | Módulo + contenedor | L | ~700 MB |
| **Nextcloud / archivos** | Buscar y resumir documentos propios | Módulo + contenedor | L | ~500 MB |
| **Correo (IMAP, solo lectura)** | Resumen de correos importantes en el resumen de buenos días | Módulo | M | — |
| **Notas y listas de la compra** | ✅ Hecho: listas de casa compartidas, listas privadas y gestión desde web, chat y Telegram | Núcleo | S | — |
| **Vaultwarden** | Gestor de contraseñas propio. ARIA solo mostraría su estado: **nunca leería contraseñas** | Módulo + contenedor | S | ~50 MB |

### 1.4 Red y seguridad

| Idea | Qué haría ARIA | Tipo | Esfuerzo | RAM |
|---|---|---|---|---|
| **Uptime Kuma** | Panel de disponibilidad de webs y servicios, con avisos | Módulo + contenedor | S | ~150 MB |
| **CrowdSec** | Bloqueo colaborativo de IPs atacantes ante el túnel y la VPN | Módulo + contenedor | M | ~150 MB |
| **Router TP-Link** | ✅ Hecho en parte: lista clientes, red de invitados y reinicio; falta el reinicio programado del mesh | Núcleo | M | — |
| **Copias de seguridad** | ✅ Hecho en parte: estado de la última copia, copia manual y aviso si está atrasada; falta restaurar un archivo concreto | Núcleo | S | — |
| **Speedtest histórico** | ✅ Hecho: test limitado cada 10 minutos y gráfica de velocidad de los últimos días | Núcleo | S | — |

### 1.5 Finanzas y vida diaria

| Idea | Qué haría ARIA | Tipo | Esfuerzo | RAM |
|---|---|---|---|---|
| **Bancos (PSD2: GoCardless Bank Account Data)** | Importar movimientos automáticamente, sin subir CSV | Módulo | L | — |
| **Precios y ofertas** | Vigilar el precio de un producto y avisar cuando baje | Módulo (usa Rutinas) | S | — |
| **Gasolineras** | ✅ Hecho: precios oficiales del Ministerio y gasolineras más baratas en un radio configurable | Núcleo | S | — |
| **Tráfico y transporte** | Incidencias de la DGT en tu ruta; horarios de autobús | Módulo | M | — |
| **Salud** | ✅ Hecho en parte: recordatorios de medicación que insisten y se confirman o posponen desde Telegram; no hay un módulo de salud separado | Núcleo | S | — |

---

## 2. Mejoras del propio ARIA (núcleo)

| Idea | Para qué | Esfuerzo |
|---|---|---|
| **Documentos propios (RAG)** | ✅ Hecho: subir PDF, TXT o MD, indexarlos con embeddings locales y preguntar con citas | L |
| **Voz sin internet de calidad** | Voz más natural en local cuando la Pi tenga margen (modelos TTS pequeños optimizados para ARM) | M |
| **Altavoz satélite** | Una Raspberry Pi Zero o un ESP32 con micrófono en otra habitación que despierte con «Aria» | L |
| **Modo familia** | ✅ Hecho en parte: perfiles de invitados y control parental por dispositivo; faltan respuestas adaptadas a perfiles infantiles | M |
| **Panel personalizable** | ✅ Hecho: elegir y ordenar las tarjetas de Inicio; se guarda en la cuenta y se aplica en tus dispositivos | M |
| **Historial de la red** | ✅ Hecho en parte: estadísticas por dispositivo de consultas y bloqueos a 24 horas o 7 días; no hay una gráfica de horas de uso | M |
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
| **Voz diseñada** | Una voz nueva creada a partir de una descripción (Qwen3-TTS VoiceDesign, Apache 2.0) y entrenada para Piper con [herramientas/voz-propia](../herramientas/voz-propia/README.md): local y sin cuotas | ⏸️ Aparcada (16/10/2026) |
| **Voz en streaming** | Empezar a hablar al terminar la primera frase | ✅ Hecho |
| **Memoria de verdad** | Búsqueda semántica local, recuerdos con fuente y confianza, olvido de lo que no se usa | ✅ Hecho |
| **Proactividad con permiso** | ARIA propone acciones ante eventos en una bandeja (aprobar o rechazar) y registra todo lo que hace | ✅ Hecho |
| **Briefing hablado** | Un minuto de voz cada mañana con lo importante (Telegram como nota de voz, HUD e Inicio) | ✅ Hecho |
| **Ojos y gestos en el HUD** | Cámara bajo petición («¿qué ves?») y control con la mano (MediaPipe, en el navegador) | ✅ Hecho |
| **Mapa 3D** | MapLibre + OpenFreeMap: edificios en 3D y «vuela a…», sin claves | ✅ Hecho |
| **ARIA flotante** | Mini-ventana siempre visible en el PC con orbe, subtítulos y micrófono | ✅ Hecho |
| **Compartir** | Reproductor local tipo VLC: carpetas, archivos, subtítulos, «Seguir viendo», atajos y pantalla completa; los archivos no se suben | ✅ Hecho |
| **Enviar a la tele** | Puente en directo para Google Cast/Chromecast/Google TV y DLNA; enlace para VLC en Apple TV y Fire TV | ✅ Hecho |

> **Voz propia diseñada (aparcada el 16/10/2026).** Idea: crear una voz con Qwen3-TTS VoiceDesign a partir de una descripción,
> generar con ella un corpus de frases y entrenar un modelo Piper en Google Colab (GPU gratis) para que ARIA hable en la propia
> máquina, sin cuotas ni internet. Lo necesario ya existe en [herramientas/voz-propia](../herramientas/voz-propia/README.md) (corpus,
> guía de grabación con consentimiento y cuaderno de Colab) y ARIA ya sabe usar un modelo Piper propio (`data/voz-propia/`). Para
> retomarlo: actualizar el cuaderno a VoiceDesign, elegir la voz entre unas muestras, entrenar e instalar el `.onnx`.

Fuera de alcance a propósito: reconocimiento facial y rastreo de información sobre personas.

## ARIA PRO 2 (16/10/2026)

Lo que aún no tiene ARIA y más aportaría (gratis, privado y viable en la Pi), por valor/esfuerzo:

| # | Mejora | Qué aporta | Esfuerzo | Estado |
|---|---|---|---|---|
| 1 | **Búsqueda global** (Ctrl+K) en notas, agenda, recordatorios, conversaciones y memoria | Encontrar cualquier cosa al momento | S | ✅ Hecho |
| 2 | **Listas compartidas** (la compra de la familia) | Lo más usado en casa | S | ✅ Hecho |
| 3 | **Mis datos**: descargar todo lo mío (ZIP) y borrar mi cuenta | Privacidad de verdad | S | ✅ Hecho |
| 4 | **Avisos meteorológicos oficiales** (Meteoalarm, sin clave) con propuestas | Útil y proactivo | S | ✅ Hecho |
| 5 | **Gasolineras más baratas** cerca (datos del Ministerio, sin clave) | Ahorro diario | S | ✅ Hecho |
| 6 | **Salud del sistema**: historial de disponibilidad de cada servicio y del túnel | Saber qué falló y cuándo | S | ✅ Hecho |
| 7 | **Atajos de Siri y Android** con tokens personales limitados | ARIA desde cualquier sitio | M | ✅ Hecho (ARIA 3.5) |
| 8 | **Tus documentos**: subir PDF, TXT o MD y preguntar sobre ellos (búsqueda local) | Un cerebro para tus papeles | M/L | ✅ Hecho |
| 9 | **Hogar con Home Assistant** (si se instala) | Luces y enchufes | M | Pendiente |
| 10 | **Ubicación para el tiempo** (opcional, ~1 km, 12 h) | El tiempo y los avisos de donde estés | S | ✅ Hecho |
| 11 | **Ping compañero** por toda la app, avisando de novedades | ARIA con más vida | S | ✅ Hecho |

No conviene: reconocimiento facial (privacidad de las visitas), leer el correo (demasiado riesgo) ni agentes que actúen sin pedir permiso.

## 3. Orden propuesto

Ordenado por lo que más aporta con menos esfuerzo y menos consumo en la Pi:

1. **Gasolineras** y **vigilar precios** (la luz ya está hecha): pequeños, útiles cada día y encajan con las rutinas.
2. **Calendario bidireccional (CalDAV)**: editar la agenda desde el móvil (ya se puede ver con la suscripción).
3. **Home Assistant**: abre la puerta a las luces, los enchufes y el robot de casa con un solo módulo.
4. **Uptime Kuma** e **historial de velocidad**: mejor vigilancia de la casa con poco consumo.
5. **Paperless-ngx**: gestión documental avanzada, pero el más pesado.
6. **Altavoz satélite**: «Aria» en toda la casa.

Antes de añadir contenedores pesados (Frigate, Paperless, Jellyfin), mira la RAM libre en ARIA → Centro de control → Sistema. ARIA, Ollama y la voz ya usan la mayor parte de los 8 GB.

## ARIA 3 — app de Android (16/10/2026)

| Fase | Qué incluye | Estado |
|---|---|---|
| **3.0** | TWA y app híbrida | ✅ Hecho |
| **3.1** | Avisos y widget con token de dispositivo | ✅ Hecho |
| **3.2** | Asistente predeterminado; palabra «Aria» experimental | ✅ Hecho |
| **3.3** | Enviar a la tele: cubierto por Compartir dentro de la app; la Pi hace de puente y nativo no hace falta por ahora | Cubierto |
| **3.4** | Widget con tiempo, próximo evento y avisos | ✅ Hecho |
| **3.5** | Atajos de Siri (iPhone) con el mismo token | ✅ Hecho |
