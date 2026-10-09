<a name="readme-top"></a>

<p align="center">
  <sub>Parte del ecosistema ARIA&nbsp;&nbsp;·&nbsp;&nbsp;<b>🤖 ARIA</b>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/SHIELD-DNS">🛡️ SHIELD-DNS</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/HEIMDALL">🔐 HEIMDALL</a></sub>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/img/banner-oscuro.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/img/banner-claro.svg">
    <img alt="ARIA: tu asistente de IA autoalojado para gestionar las apps de casa" src="docs/img/banner-oscuro.svg" width="100%">
  </picture>
</p>

<p align="center">
  <a href="LICENSE"><img alt="Licencia MIT" src="https://img.shields.io/badge/licencia-MIT-38d6ff?style=flat-square"></a>
  <img alt="100 % autoalojado" src="https://img.shields.io/badge/100%20%25-autoalojado-34d399?style=flat-square">
  <img alt="Gratis" src="https://img.shields.io/badge/precio-gratis-7c8cff?style=flat-square">
  <img alt="Docker Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white">
  <img alt="Raspberry Pi arm64" src="https://img.shields.io/badge/Raspberry%20Pi-arm64-C51A4A?style=flat-square&logo=raspberrypi&logoColor=white">
  <img alt="Linux amd64 y arm64" src="https://img.shields.io/badge/Linux-amd64%20%7C%20arm64-FCC624?style=flat-square&logo=linux&logoColor=black">
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="En español" src="https://img.shields.io/badge/idioma-espa%C3%B1ol-f5b84b?style=flat-square">
</p>

<p align="center">
  <b><a href="#-inicio-rápido-5-minutos">🚀 Instalar</a></b>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="docs/INSTALACION.md">📘 Guía de instalación</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="docs/USO.md">🧭 Guía de uso</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="docs/MODULOS.md">🧩 Módulos</a>&nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="docs/PLAN.md">🗺️ Hoja de ruta</a>
</p>

**ARIA es un asistente de inteligencia artificial autoalojado que gestiona tus aplicaciones de casa.** Se instala con un comando en una Raspberry Pi o en un PC con Linux, se abre desde el navegador o el móvil y entiende español: le hablas o le escribes y ella consulta, enciende, pausa o te avisa.

ARIA se amplía con **módulos**: cada aplicación que añades aparece en su página de Inicio, gana herramientas en el chat y puede mandarte avisos. Trae dos aplicaciones integradas como ejemplo, [SHIELD-DNS](https://github.com/BertMarti/SHIELD-DNS) (bloqueador de anuncios) y [HEIMDALL](https://github.com/BertMarti/HEIMDALL) (VPN), pero puedes añadir todas las que quieras.

<table>
  <tr>
    <td width="33%" valign="top"><h3>💸 Gratis</h3>Usa capas gratuitas de IA en la nube (Ollama Cloud, Groq, Gemini) y, si fallan, un modelo local.</td>
    <td width="33%" valign="top"><h3>🏠 Tuyo</h3>Corre en tu máquina, con tus usuarios y tus datos en una carpeta <code>data/</code>.</td>
    <td width="33%" valign="top"><h3>👨‍👩‍👧 Para toda la casa</h3>Varios usuarios con roles, app instalable en el móvil, Telegram y notificaciones.</td>
  </tr>
</table>

<p align="center">
  <img alt="Modo HUD de ARIA: orbe animado sobre una rejilla futurista, con tarjetas de clima, agenda, pendientes, finanzas, estado de la casa, red, precio de la luz y mercados" src="docs/img/captura-hud.png" width="100%">
  <br><sub><b>Modo HUD</b>: la presencia de ARIA a pantalla completa. Tarjetas de cristal que siguen al ratón, un orbe que cambia de color al escuchar, pensar y hablar (y ondula con su voz), y acciones rápidas.</sub>
</p>

<p align="center">
  <img alt="Página de Inicio de ARIA: menú de tarjetas numeradas (HUD, resumen del día, agenda, tu casa, información, mapa, chat, finanzas) y debajo el resumen del día" src="docs/img/captura-inicio.png" width="100%">
  <br><sub><b>Inicio</b>: un menú de tarjetas numeradas con un dato vivo en cada una (el tiempo, tu próxima cita, los dispositivos de casa…) y su estado, y debajo el resumen del día con ▶ <b>Escuchar</b>. Instancia de demostración con datos ficticios.</sub>
</p>

### 🧚 Conoce a Ping

<table>
  <tr>
    <td width="58%"><img alt="Escaparate público de ARIA: marca ARIA gigante, el orbe y Ping, un hada de luz holográfica, revoloteando junto al logotipo" src="docs/img/captura-escaparate.png"></td>
    <td width="42%"><img alt="Demo «Tu casa» del escaparate: Ping junto a los anuncios atrapados, los dispositivos de la red y la VPN" src="docs/img/captura-ping.png"></td>
  </tr>
</table>

**Ping** es la compañera de ARIA: una pequeña **hada de luz holográfica** que vive en la red de casa. Atrapa los anuncios (SHIELD-DNS), vigila quién entra por la VPN (HEIMDALL) y lleva la cuenta de todo con mucho orgullo: «¡Eh, mira! 1.284 anuncios atrapados hoy».

- **Cambia de color según lo que pasa**: cian si todo va bien, ámbar si hay algo que mirar, rosa si es una alerta y violeta mientras piensa.
- **Tiene voz propia**, muy aguda y traviesa, y un tintineo de tres notas compuesto para ARIA. Cuando ARIA la presenta («…esa lucecita nerviosa es Ping»), ARIA hace una pausa y Ping suelta su «¡Eh, mira!».
- **Vuela sola**: al principio sigue tu ratón y luego revolotea por libre. Está dibujada en un `<canvas>` propio, sin imágenes externas, y respeta «reducir movimiento».

Ping se estrena en el **escaparate público** de ARIA (`/hola`): una página estática que enseña qué es ARIA a cualquiera sin exponer nada de casa (datos de ejemplo, voz pregrabada, sin servidor ni analítica). Tiene una portada con el orbe, el interruptor **«Quiero escuchar a ARIA»** para que se presente con su voz, un menú de demos, «Qué funciona hoy» y unas preguntas con respuesta.

> Ping está inspirada en el espíritu de las hadas guía de los videojuegos clásicos, pero su diseño, su nombre, su voz y sus sonidos son originales de ARIA.

### 🆕 Novedades

| | Qué hay de nuevo |
|:---:|---|
| 🧚 | **Escaparate «Conoce a ARIA»** (`/hola`) y **Ping**, su hada de luz con voz propia: ARIA se presenta con su voz y Ping la interrumpe con un «¡Eh, mira!». Página pública y estática, sin datos reales. |
| 🔢 | **Inicio en tarjetas numeradas**: 01 HUD · 02 Resumen del día · 03 Agenda · 04 Tu casa · 05 Información · 06 Mapa · 07 Chat · 08 Finanzas, cada una con un dato vivo y su estado (ACTIVO, AVISO, PRONTO). |
| 🎧 | **Briefing hablado**: el resumen del día contado por ARIA en un minuto. Por Telegram cada mañana como **nota de voz** (y con el botón **🔊 Escuchar**), en el HUD (**Briefing del día**) y en Inicio (**▶ Escuchar**). Se sintetiza una vez y se guarda, así que apenas gasta cuota de voz. |
| 🌌 | **Modo HUD** (`#hud`): escena futurista con rejilla animada, orbe que «mira» al ratón y tarjetas que se iluminan y giran en 3D al pasar por encima. **Opciones**: qué tarjetas ver, 5 colores, efectos, reloj con segundos y voz. **Modo quiosco** para una tableta (pantalla siempre encendida, controles que se esconden). |
| ⚡ | **Precio de la luz** (PVPC de España, sin claves): precio de ahora, horas más baratas y caras, gráfico de las 24 horas en Inicio y el HUD, y en el chat («¿cuándo pongo la lavadora?»). |
| 📲 | **Agenda en el móvil**: suscríbete desde el calendario del iPhone, Android u Outlook con un enlace privado (se actualiza solo) o descarga un `.ics`. |
| 🗣️ | **Elige la voz de ARIA**: 14 voces femeninas, tono (dulce, alegre, serena o muy tierna) y acento de España o latino, con ▶ para escucharlas antes. |
| 🔐 | **Verificación en dos pasos** con cualquier app de autenticación (Google Authenticator, Aegis, 1Password…) y códigos de recuperación. |
| 📰 | **Resumen diario** bien maquetado en **Inicio**, en el **HUD** y por **Telegram** cada mañana: tiempo, luz, salud de las aplicaciones, red, finanzas, inversiones (también Bitcoin y Ethereum con gráfica), agenda y cumpleaños. En Telegram llega con botones: Abrir ARIA, Agenda, Actualizar y Pausar anuncios. |
| 📅 | **Agenda y cumpleaños**: calendario mensual, semanal y en lista, eventos que se repiten, avisos antes de cada cita y de cada cumpleaños. También por chat («apúntame el dentista el jueves a las 17:30»). |
| 🗺️ | **Mapa libre** con OpenStreetMap: buscar lugares, tu ubicación, rutas y «farmacias cerca», sin claves ni seguimiento. |
| 📈 | **Información**: noticias por temas con resumen y fuentes, y **Mis inversiones** (acciones, fondos, ETF y cripto en euros con gráfica, variación y tu posición). |
| 🖥️ | **Sistema en directo**: CPU, memoria y red por contenedor, temperatura y un botón seguro para **reiniciar la Raspberry** desde la web o Telegram. |
| ⚙️ | **Automatizaciones** «si pasa esto, haz aquello», **estadísticas por dispositivo** de la red, **informe semanal** y **proyectos y decisiones** en la memoria. |
| 🎨 | **Interfaz pulida**: Ajustes por secciones con buscador, la Red en fichas legibles en el móvil, noticias en tarjetas con su fuente y resumen limpio, y manos libres que ya no «oye» un «Gracias.» fantasma en el PC. |

## 📑 Índice

- [✨ Qué puede hacer](#-qué-puede-hacer)
- [📸 Capturas](#-capturas)
- [🧚 Conoce a Ping](#-conoce-a-ping)
- [🧩 Cómo está hecha](#-cómo-está-hecha)
  - [🎙️ Cómo funciona la voz](#️-cómo-funciona-la-voz)
- [📋 Requisitos](#-requisitos)
- [🚀 Inicio rápido (5 minutos)](#-inicio-rápido-5-minutos)
- [📚 Guías](#-guías)
- [⚙️ Configuración](#️-configuración)
- [🔌 Añade tus propias aplicaciones (módulos)](#-añade-tus-propias-aplicaciones-módulos)
- [🧠 Cerebros: de dónde salen las respuestas](#-cerebros-de-dónde-salen-las-respuestas)
- [🔒 Seguridad y privacidad](#-seguridad-y-privacidad)
- [🐳 Contenedores y puertos](#-contenedores-y-puertos)
- [🆘 Problemas frecuentes](#-problemas-frecuentes)
- [🛠️ Para desarrolladores](#️-para-desarrolladores)
- [🗺️ Hoja de ruta](#️-hoja-de-ruta)
- [🌐 El ecosistema ARIA](#-el-ecosistema-aria)
- [📄 Licencia](#-licencia)

## ✨ Qué puede hacer

| | Grupo | Qué incluye |
|:---:|---|---|
| 💬 | **Asistente y chat** | Chat con conversaciones guardadas, respuestas en directo, botón Detener, copiar y Markdown.<br>**Agentes especializados**: ARIA (general), `@finanzas`, `@redes` y `@seguridad`. ARIA elige el adecuado sola o lo eliges tú.<br>**Búsqueda en internet y noticias** con un metabuscador propio (SearXNG), citando las fuentes.<br>**Resumir enlaces** que pegas o compartes desde el móvil.<br>**Visión**: mándale una foto y pregúntale por ella; si es un ticket, te propone apuntar el gasto. |
| 🎙️ | **Voz** | Micrófono (pulsar para hablar), botón **Leer** en cada respuesta y modo **manos libres**: dices «Aria» y tu pregunta.<br>**Briefing hablado** del día (un minuto) en Telegram, el HUD e Inicio.<br>Voz natural en la nube con respaldo local en tu máquina; transcripción en la nube con respaldo local. Ver [cómo funciona la voz](#-cómo-funciona-la-voz). |
| 🧠 | **Memoria y automatización** | **Memoria**: recuerda datos tuyos («recuerda que…») y escribe un **diario** de cada día.<br>**Resumen de buenos días** en Inicio, en el chat y, si quieres, por Telegram o notificación.<br>**Recordatorios** en lenguaje natural («recuérdame mañana a las 9…») y **rutinas** programadas («cada mañana a las 8, dime el tiempo y tres titulares»). |
| 🔔 | **Avisos y canales** | Campana de avisos en la web, **bot de Telegram** propio y **notificaciones push** en el móvil o el navegador.<br>Vigila la casa sola: servicios caídos, dispositivos desconocidos, temperatura, disco, copias atrasadas… |
| 🏡 | **Tu casa y tu red** | **Finanzas personales**: movimientos, categorías, presupuestos e importación del CSV del banco.<br>**Inventario de red**: dispositivos de la LAN, latencia, test de velocidad e historial.<br>**Seguridad**: escaneo defensivo de puertos de tu red y búsqueda de vulnerabilidades conocidas.<br>**Control parental** por dispositivo (pausar internet, bloquear TikTok, YouTube…, horarios), mediante SHIELD-DNS. |
| 🧩 | **Aplicaciones (módulos)** | **SHIELD-DNS**: estadísticas, pausar y reanudar el bloqueo de anuncios.<br>**HEIMDALL**: ver, crear, activar y desactivar dispositivos de la VPN con su código QR.<br>**Uptime web** (módulo de ejemplo): «¿responde example.org?» y avisos si una web se cae.<br>**Las tuyas**: un mosaico en Inicio, herramientas en el chat, avisos y endpoints propios. Ver [docs/MODULOS.md](docs/MODULOS.md).<br>Spotify y Netflix existen en el código pero están **aparcados** (desactivados por defecto, `ARIA_SPOTIFY=0` / `ARIA_NETFLIX=0`). |
| 📅 | **Agenda, mapa e información** | **Agenda** con calendario (mes, semana, lista), eventos repetidos y **cumpleaños** con aviso; **suscripción** desde el calendario del móvil.<br>**Mapa** OpenStreetMap: búsqueda, ubicación, rutas y lugares cercanos.<br>**Información**: noticias por temas y **Mis inversiones** con gráficas en euros. |
| 🌌 | **HUD y resumen diario** | **Modo HUD** futurista con tarjetas interactivas, opciones y modo quiosco.<br>**Resumen diario** en Inicio, HUD y Telegram (HTML bien maquetado, con botones).<br>**Precio de la luz** por horas (PVPC). |
| 🖥️ | **Sistema** | Telemetría en directo por contenedor, **reinicio seguro** firmado (HMAC) y **automatizaciones**. HEIMDALL admite accesos **temporales** y avisa si una VPN conecta desde un país u operador nuevo (solo se consulta la IP pública). |
| 🔑 | **Acceso y usuarios** | HTTPS automático en tu red (`https://aria.local`, la IP o `https://aria.lan`).<br>Opcional: tu dominio con **Cloudflare Tunnel + Access**, sin abrir puertos y con inicio de sesión único.<br>Varios usuarios con rol **administrador** o **usuario**; permisos comprobados en el servidor; **verificación en dos pasos** opcional.<br>Paleta de órdenes **Ctrl+K**, app instalable (PWA) y menú **Compartir** de Android. |

<p align="right"><a href="#readme-top">⬆️ Volver arriba</a></p>

## 📸 Capturas

> [!NOTE]
> Todas las capturas salen de una instancia de demostración con **datos ficticios** (Ana, Lucía, red `192.168.1.x`). Las respuestas del chat son de ejemplo.

<table>
  <tr>
    <td width="50%"><img alt="Panel de opciones del HUD: tarjetas visibles, colores, efectos y modo quiosco" src="docs/img/captura-hud-opciones.png"><p align="center"><sub><b>HUD → Opciones</b>: tarjetas, 5 colores, efectos y modo quiosco</sub></p></td>
    <td width="50%"><img alt="Ajustes organizados por secciones, con buscador" src="docs/img/captura-ajustes.png"><p align="center"><sub><b>Ajustes</b>: por secciones y con buscador</sub></p></td>
  </tr>
  <tr>
    <td width="50%"><img alt="Agenda con calendario mensual, eventos y cumpleaños" src="docs/img/captura-agenda.png"><p align="center"><sub><b>Agenda</b>: calendario del mes, el día elegido y los próximos cumpleaños</sub></p></td>
    <td width="50%"><img alt="Resumen diario de ARIA tal como llega por Telegram" src="docs/img/captura-telegram.png"><p align="center"><sub><b>Telegram</b>: el resumen de cada mañana</sub></p></td>
  </tr>
  <tr>
    <td><img alt="Información: Mis inversiones con gráficas y noticias por temas" src="docs/img/captura-informacion.png"><p align="center"><sub><b>Información</b>: inversiones en euros y noticias por temas</sub></p></td>
    <td><img alt="Mapa de OpenStreetMap con búsqueda y lugares cercanos" src="docs/img/captura-mapa.png"><p align="center"><sub><b>Mapa</b>: OpenStreetMap, sin claves ni seguimiento</sub></p></td>
  </tr>
  <tr>
    <td width="50%"><img alt="Chat con ARIA: pregunta por el estado de la casa y pausa del bloqueador" src="docs/img/captura-chat.png"><p align="center"><sub><b>Chat</b>: herramientas en vivo y el cerebro que respondió</sub></p></td>
    <td width="50%"><img alt="Página Red con el inventario de dispositivos de casa" src="docs/img/captura-red.png"><p align="center"><sub><b>Red</b>: inventario, latencia y un dispositivo desconocido</sub></p></td>
  </tr>
  <tr>
    <td><img alt="Ventana de control parental de un dispositivo" src="docs/img/captura-control-parental.png"><p align="center"><sub><b>Control parental</b>: pausar, bloquear servicios y horarios</sub></p></td>
    <td><img alt="Ajustes, sección Módulos, con SHIELD-DNS, HEIMDALL y Uptime web" src="docs/img/captura-modulos.png"><p align="center"><sub><b>Ajustes → Módulos</b>: integradas y las tuyas</sub></p></td>
  </tr>
  <tr>
    <td><img alt="Panel de avisos abierto desde la campana" src="docs/img/captura-avisos.png"><p align="center"><sub><b>Avisos</b>: la campana de la casa</sub></p></td>
    <td><img alt="Ajustes, sección Rutinas" src="docs/img/captura-rutinas.png"><p align="center"><sub><b>Rutinas</b>: tareas que ARIA hace sola</sub></p></td>
  </tr>
  <tr>
    <td colspan="2"><img alt="Menú del escaparate público con cinco tarjetas numeradas: su presencia, tu tiempo, red VPN y anuncios con Ping, el mundo resumido y qué funciona hoy" src="docs/img/captura-escaparate-menu.png"><p align="center"><sub><b>Escaparate</b> (<code>/hola</code>): cada tarjeta abre una demo de solo lectura con datos de ejemplo</sub></p></td>
  </tr>
</table>

<details>
<summary><b>📱 Más capturas: móvil, Centro de control, semana y Finanzas</b></summary>
<br>

<p align="center">
  <img alt="Inicio de ARIA en el móvil" src="docs/img/captura-movil-inicio.png" width="230">
  &nbsp;
  <img alt="Modo HUD en el móvil" src="docs/img/captura-movil-hud.png" width="230">
  &nbsp;
  <img alt="Agenda en lista en el móvil" src="docs/img/captura-movil-agenda.png" width="230">
  &nbsp;
  <img alt="Chat del agente Redes en el móvil" src="docs/img/captura-movil-chat.png" width="230">
</p>

<p align="center">
  <img alt="Dispositivos de la red en fichas, en el móvil" src="docs/img/captura-movil-red.png" width="230">
  &nbsp;
  <img alt="Ajustes en el móvil, con pestañas de secciones" src="docs/img/captura-movil-ajustes.png" width="230">
  &nbsp;
  <img alt="Escaparate público de ARIA en el móvil, con Ping" src="docs/img/captura-movil-escaparate.png" width="230">
</p>

<p align="center"><img alt="Centro de control con SHIELD-DNS, HEIMDALL y el sistema en directo por contenedor" src="docs/img/captura-centro-control.png" width="100%"><br><sub><b>Centro de control</b>: SHIELD-DNS, HEIMDALL, el sistema en directo y el reinicio seguro</sub></p>

<p align="center"><img alt="Agenda en vista semanal" src="docs/img/captura-agenda-semana.png" width="100%"><br><sub><b>Agenda → Semana</b></sub></p>

<p align="center"><img alt="Finanzas: resumen del mes, gastos por categoría y presupuestos" src="docs/img/captura-finanzas.png" width="100%"><br><sub><b>Finanzas</b>: resumen del mes, categorías y presupuestos</sub></p>

</details>

<p align="right"><a href="#readme-top">⬆️ Volver arriba</a></p>

## 🧩 Cómo está hecha

ARIA es un **núcleo** (la app web, el chat y los cerebros) y un **cargador de módulos**. Cada aplicación de tu casa se conecta como un módulo: las integradas (SHIELD-DNS y HEIMDALL) vienen de serie y las tuyas se añaden como carpetas en `modulos/`.

```mermaid
flowchart LR
    U["📱 Navegador / móvil<br/>Telegram"] --> C["🔒 Caddy HTTPS<br/>puertos 80/443"]
    C --> A["🤖 ARIA app<br/>chat · agentes · avisos · rutinas"]
    A --> CB["🧠 Cerebros<br/>Ollama Cloud → Groq → Gemini → local"]
    A --> S["🔎 SearXNG<br/>búsqueda"]
    A --> V["🎙️ aria-voz<br/>voz local"]
    A --> E["🛰️ aria-escaner<br/>nmap defensivo"]
    A --> M{{"🧩 Módulos"}}
    M --> M1["🛡️ SHIELD-DNS<br/>integrado"]
    M --> M2["🔐 HEIMDALL<br/>integrado"]
    M --> M3["🌍 uptime<br/>ejemplo"]
    M --> M4["✨ tu-app<br/>modulos/tu-app"]
```

<details>
<summary>Si tu visor no muestra el diagrama, aquí está el mismo esquema en texto</summary>

```
 Navegador / móvil / Telegram
              │
        Caddy (HTTPS 80/443)
              │
          ARIA (núcleo) ───── Cerebros: Ollama Cloud → Groq → Gemini → local (Ollama)
          │   │   │  └────── SearXNG (búsqueda) · aria-voz (voz) · aria-escaner (red)
          │   │   │
   ┌──────┴───┴───┴──────────────┐
   │          Módulos            │
   ├─ SHIELD-DNS  (integrado)    │  bloqueador de anuncios (Pi-hole)
   ├─ HEIMDALL    (integrado)    │  VPN WireGuard (wg-easy)
   ├─ uptime      (ejemplo)      │  ¿responde esta web?
   └─ tu-app      (modulos/…)    │  lo que tú quieras
```

</details>

### Qué pasa cuando le preguntas algo

```mermaid
sequenceDiagram
    autonumber
    actor T as Tú
    participant C as Caddy HTTPS
    participant A as ARIA
    participant IA as Cerebro de IA
    participant H as Herramienta o módulo
    T->>C: «¿Cuántos anuncios has bloqueado hoy?»
    C->>A: Petición con tu sesión
    A->>A: Elige el agente y comprueba tus permisos
    A->>IA: Pregunta y herramientas disponibles
    IA-->>A: Quiero usar «estado_bloqueador»
    A->>H: Consulta a SHIELD-DNS
    H-->>A: Datos en vivo
    A->>IA: Resultado de la herramienta
    IA-->>A: Respuesta redactada
    A-->>T: Respuesta en directo con la insignia del cerebro y del agente
```

### 🎙️ Cómo funciona la voz

| Paso | Qué se usa | Respaldo | Dónde ocurre |
|---|---|---|---|
| **Oír «Aria»** (manos libres) | Detector de palabra clave en `aria-voz` | — | Siempre en tu máquina: el sonido no sale de casa |
| **Entender lo que dices** | Whisper en **Groq** (gratis, muy rápido) | **faster-whisper** en `aria-voz` | Nube o tu máquina |
| **Hablar** | **Gemini TTS**: 14 voces femeninas, con tono y acento de España | **Piper** en `aria-voz` (voz femenina española) o tu **voz propia** | Nube o tu máquina |
| **Notas de voz de Telegram** | La misma voz, convertida a OGG/Opus en `aria-voz` | WAV | Tu máquina |
| **Escaparate y Ping** | Audio **pregrabado** (MP3) | Subtítulos | El navegador del visitante |

- **Cuota**: la capa gratuita de Gemini da pocas síntesis al día. Por eso las muestras de voces, las frases repetidas y el **briefing hablado** se guardan, y cuando la cuota se agota ARIA habla con Piper y avisa hasta qué hora.
- **Voz propia**: si dejas un modelo Piper (`.onnx` + `.onnx.json`) en `data/voz-propia/`, ARIA puede usarlo como voz sin internet ni cuotas. En [`herramientas/voz-propia/`](herramientas/voz-propia/) tienes cómo grabarla (siempre con el consentimiento de quien pone la voz) y un cuaderno para entrenarla gratis en Google Colab.
- **Privacidad**: el audio que grabas no se guarda nunca; solo se transcribe y se descarta.

<p align="right"><a href="#readme-top">⬆️ Volver arriba</a></p>

## 📋 Requisitos

| | Mínimo | Recomendado |
|---|---|---|
| 🖥️ Máquina | Raspberry Pi 4/5 o PC/mini-PC con Linux (arm64 o amd64) | Raspberry Pi 5 o mini-PC |
| 🧮 RAM | 4 GB (usando sobre todo los cerebros en la nube y un modelo local pequeño) | 8 GB o más |
| 💾 Disco | 16 GB libres | 32 GB libres, mejor en SSD |
| 🐧 Sistema | Raspberry Pi OS 64 bits, Debian o Ubuntu | Raspberry Pi OS 64 bits (Bookworm) |
| 🐳 Software | Docker con `docker compose` v2 (el instalador ofrece instalarlo) | — |
| 🌐 Red | Puertos 80 y 443 libres en la máquina | IP fija para la máquina (reserva DHCP en el router) |

Las imágenes de Docker ocupan unos 10 GB (la de Ollama es la mayor) y el modelo local por defecto, unos 2 GB.

> [!WARNING]
> **Windows**: ARIA no está probada en Windows. Con WSL2 la parte web podría funcionar, pero el escáner de red, SHIELD-DNS (puerto 53) y HEIMDALL (WireGuard) necesitan ver tu red de verdad, y eso en WSL2/Docker Desktop no está garantizado. Para algo fiable usa una Raspberry Pi o un PC con Linux.

## 🚀 Inicio rápido (5 minutos)

```mermaid
flowchart LR
    A["1️⃣ Clonar<br/>en ~/homelab"] --> B["2️⃣ ./install.sh"]
    B --> C{"¿Docker<br/>instalado?"}
    C -- "No" --> D["Lo instala:<br/>cierra sesión y repite"]
    D --> B
    C -- "Sí" --> E["3️⃣ Entrar en<br/>aria.local"]
    E --> F["4️⃣ Iniciar sesión<br/>admin + contraseña"]
    F --> G["5️⃣ Opcional:<br/>clave gratuita de IA"]
```

**1. Clona el repositorio** en `~/homelab` (los scripts de copias y de Cloudflare esperan esa carpeta):

```bash
mkdir -p ~/homelab && cd ~/homelab
git clone https://github.com/BertMarti/ARIA.git && cd ARIA
```

> ✅ **Comprobación:** `ls` muestra `install.sh`, `docker-compose.yml` y la carpeta `docs/`.

**2. Instala**:

```bash
./install.sh
```

Si no tienes Docker, te ofrece instalarlo; después cierra sesión, vuelve a entrar y repite `./install.sh`.

> ✅ **Comprobación:** al terminar, el instalador muestra la dirección, el usuario y la contraseña, y `docker compose ps` lista los contenedores en marcha (`healthy`).

**3. Entra** en `https://aria.local` (o `https://192.168.1.50`, con la IP de tu máquina). El navegador avisará del certificado: es lo esperado la primera vez.

> ✅ **Comprobación:** ves la pantalla de inicio de sesión de ARIA.

**4. Inicia sesión** con el usuario `admin` y la contraseña que muestra el instalador (también está en `ARIA_PASSWORD` dentro del archivo `.env`).

> ✅ **Comprobación:** aparece **Inicio** con tu resumen del día y los mosaicos de tus aplicaciones.

**5. Opcional, pero recomendado**: añade una clave gratuita de Groq o Gemini (o conecta Ollama Cloud) para respuestas rápidas. Ver [Claves gratuitas](docs/INSTALACION.md#6-claves-gratuitas-de-ia-opcional).

> ✅ **Comprobación:** en **Ajustes → Cerebros** el cerebro aparece con «clave configurada» y **Probar** responde.

> [!TIP]
> ¿Quieres también el bloqueador de anuncios y la VPN? Instala las tres aplicaciones de una vez:
>
> ```bash
> curl -fsSL https://raw.githubusercontent.com/BertMarti/ARIA/main/instalar-todo.sh | bash
> ```
>
> Las instala en este orden: SHIELD-DNS, HEIMDALL y ARIA. Todos los detalles, en la [guía de instalación](docs/INSTALACION.md#opción-b-aria--shield-dns--heimdall-de-una-vez).

<p align="right"><a href="#readme-top">⬆️ Volver arriba</a></p>

## 📚 Guías

| Guía | Para qué |
|---|---|
| 📘 [Instalación paso a paso](docs/INSTALACION.md) | Hardware, Docker, primer acceso, claves gratuitas, certificado, dominio propio, router, Telegram, copias, actualizar y problemas frecuentes |
| 🧭 [Guía de uso](docs/USO.md) | Cada sección de la web, frases de ejemplo, agentes, voz, memoria, rutinas, Telegram, control parental, usuarios |
| 🧩 [Módulos](docs/MODULOS.md) | Conectar tus propias aplicaciones a ARIA (para desarrolladores) |
| 🗺️ [Hoja de ruta](docs/PLAN.md) | Ideas de lo que puede venir |

## ⚙️ Configuración

Toda la configuración está en el archivo `.env` (lo crea `install.sh` a partir de [`.env.example`](.env.example)). Tras editarlo, aplica los cambios con:

```bash
docker compose up -d
```

> [!IMPORTANT]
> Algunos ajustes se cambian también desde la web y entonces **la web manda** sobre `.env`: el orden de los cerebros (Ajustes → Cerebros, guardado en `data/cerebros.json`), el modelo local activo (`data/model.txt`) y la contraseña (si la cambias en Ajustes).

<details>
<summary><b>📋 Variables principales</b> (la lista completa y comentada está en <code>.env.example</code>)</summary>
<br>

| Área | Variable | Por defecto | Para qué |
|---|---|---|---|
| Acceso | `ARIA_USER` | `admin` | Administrador inicial |
| | `ARIA_PASSWORD` | aleatoria (la genera `install.sh`) | Su contraseña |
| | `ARIA_SECRET` | aleatorio | Firma de las sesiones |
| Red | `ARIA_LAN_IP` | la detecta `install.sh` | IP de la máquina en tu red |
| | `ARIA_HOSTS` | IP, `<nombre>.local`, `localhost`, `aria.local`, `aria.lan` | Nombres con los que puedes entrar (y para los que se emite certificado) |
| Cerebros | `ARIA_CEREBROS` | `ollama_cloud,groq,gemini,local` | Orden de la cadena de IA |
| | `GROQ_API_KEY` | vacía | Clave gratuita de Groq (chat, voz y visión) |
| | `GEMINI_API_KEY` | vacía | Clave gratuita de Gemini (chat, voz y visión) |
| | `ARIA_MODELO_OLLAMA_CLOUD` | `gpt-oss:120b-cloud` | Modelo de Ollama Cloud |
| | `ARIA_MODELO_GROQ` | `openai/gpt-oss-120b` | Modelo de Groq |
| | `ARIA_MODELO_GEMINI` | `gemini-3.1-flash-lite` | Modelo de Gemini |
| | `ARIA_NOMBRE_USUARIO` | vacío | Cómo te llama ARIA (vacío = tu nombre de usuario) |
| Modelo local | `ARIA_MODEL` | `llama3.2:3b` | Modelo de respaldo en tu máquina |
| | `OLLAMA_MEM_LIMIT` | `5g` | Memoria máxima de Ollama |
| | `ARIA_NUM_CTX` | `4096` | Contexto del modelo local (menos = menos RAM) |
| | `OLLAMA_KEEP_ALIVE` | `5m` | Cuánto se queda cargado en RAM |
| General | `ARIA_TZ` | `Europe/Madrid` | Zona horaria |
| | `ARIA_CIUDAD` | vacía | Ciudad para el tiempo (p. ej. `Madrid`); vacía = sin tiempo |
| Búsqueda | `SEARXNG_SECRET` | aleatorio | Clave interna del buscador |
| Integraciones | `SHIELD_URL` | vacía = `http://<ARIA_LAN_IP>:8080` (revisa que lleve tu IP) | Dirección de SHIELD-DNS |
| | `SHIELD_PASSWORD` | se copia de `../SHIELD-DNS/.env` | Contraseña de Pi-hole |
| | `VPN_URL` | vacía = `https://<ARIA_LAN_IP>:51843` (revisa que lleve tu IP) | Dirección de HEIMDALL |
| | `VPN_USER`, `VPN_PASSWORD` | se copian de `../HEIMDALL/.env` | Usuario y contraseña de wg-easy |
| Red y seguridad | `ARIA_RED_PERMITIDA` | una red /24 de ejemplo: **pon la tuya**, p. ej. `192.168.1.0/24` | Única red que ARIA puede escanear |
| | `ARIA_ROUTER_IP` | **pon la tuya**, p. ej. `192.168.1.1` | IP del router (nunca se pausa) |
| Control parental | `ARIA_CONTROL` | `1` | `0` lo desactiva |
| | `ARIA_CONTROL_PROTEGIDOS` | vacía | IP extra que nunca se pueden pausar |
| Avisos | `ARIA_URL_PUBLICA` | `https://aria.tu-dominio.com` | Tu dirección pública; **déjala vacía si no usas dominio** |
| | `TELEGRAM_BOT_TOKEN` | vacío | Token del bot (vacío = bot apagado) |
| | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | las genera `install.sh` | Notificaciones push |
| SSO (opcional) | `ARIA_CF_ACCESS_TEAM`, `ARIA_CF_ACCESS_AUD` | vacías | Inicio de sesión con Cloudflare Access |
| | `ARIA_ADMIN_EMAILS` | vacía | Emails que siempre son administradores |
| Módulos | `ARIA_MODULOS` | vacía (= todos) | Qué módulos se cargan (`-` = ninguno) |
| | `UPTIME_URLS` | vacía | Webs que vigila el módulo `uptime` |
| Aparcados | `ARIA_SPOTIFY`, `ARIA_NETFLIX` | `0` | Reactivan Spotify / Netflix |
| Precio de la luz | `ARIA_LUZ` | `1` | PVPC de España (Red Eléctrica). Ponlo a `0` fuera de España |

</details>

<p align="right"><a href="#readme-top">⬆️ Volver arriba</a></p>

## 🔌 Añade tus propias aplicaciones (módulos)

Un módulo es una carpeta en `modulos/`. ARIA lo carga al arrancar y lo enchufa en varios sitios a la vez:

```mermaid
flowchart LR
    subgraph CARPETA["📁 modulos/tu-app/"]
        J["modulo.json<br/>manifiesto"]
        P["modulo.py<br/>opcional"]
    end
    J --> L["⚙️ Cargador de módulos<br/>al arrancar ARIA"]
    P --> L
    L --> I["🏠 Mosaico en Inicio<br/>con punto de salud"]
    L --> HT["💬 Herramientas en el chat<br/>Telegram y rutinas"]
    L --> AV["🔔 Avisos periódicos"]
    L --> EP["🔗 Endpoints propios<br/>/api/modulos/tu-app/"]
    L --> AJ["🧩 Ajustes → Módulos"]
```

El más sencillo solo necesita un `modulo.json` y ya pone un mosaico en Inicio con un punto verde o rojo según si tu aplicación responde:

```bash
cp -r modulos/_plantilla modulos/recetas
rm modulos/recetas/modulo.py modulos/recetas/compose.ejemplo.yml
```

`modulos/recetas/modulo.json`:

```json
{
  "id": "recetas",
  "nombre": "Recetas",
  "version": "1.0.0",
  "icono": "casa",
  "url": "http://{host}:8099/",
  "salud": {"tipo": "http", "host": "host.docker.internal", "puerto": 8099, "ruta": "/"},
  "roles": ["admin", "usuario"]
}
```

```bash
docker compose restart app
```

> ✅ **Comprobación:** en **Ajustes → Módulos** aparece «Recetas» y en Inicio, su mosaico.

Con un `modulo.py` puedes añadir además herramientas al chat («¿qué receta toca hoy?»), avisos periódicos y endpoints propios. Todo está explicado, con la referencia del SDK, en **[docs/MODULOS.md](docs/MODULOS.md)**.

> [!WARNING]
> Un módulo con `modulo.py` es código que se ejecuta dentro de ARIA. Instala solo módulos que hayas leído o de fuentes de confianza.

## 🧠 Cerebros: de dónde salen las respuestas

ARIA prueba una **cadena de cerebros gratuitos** en orden. Si uno falla (límite gratuito agotado, clave rechazada, sin conexión o más de 30 s sin responder), pasa al siguiente sin que lo notes. Cada respuesta lleva una insignia con el cerebro que la dio.

```mermaid
flowchart LR
    Q["💬 Tu pregunta"] --> O["1 · Ollama Cloud"]
    O -- "falla" --> G["2 · Groq"]
    G -- "falla" --> M["3 · Google Gemini"]
    M -- "falla" --> L["4 · Local Ollama<br/>sin internet"]
    O -- "responde" --> R["✅ Respuesta<br/>con insignia"]
    G -- "responde" --> R
    M -- "responde" --> R
    L --> R
```

| # | Cerebro | Clave | Notas |
|---|---|---|---|
| 1 | Ollama Cloud | tu cuenta de Ollama (`docker exec -it aria-ollama ollama signin`) | Plan gratuito con límites |
| 2 | Groq | `GROQ_API_KEY` | Gratis; también transcribe la voz |
| 3 | Google Gemini | `GEMINI_API_KEY` | Gratis; también la voz de ARIA y la visión |
| 4 | Local (Ollama) | ninguna | Funciona sin internet, pero es mucho más lento |

Sin ninguna clave, ARIA funciona solo con el modelo local. Orden y activación: **Ajustes → Cerebros** (con botón **Probar**). El cerebro local no se puede desactivar: es el último recurso.

<details>
<summary><b>🎙️ ¿Y la voz, la transcripción y la visión?</b></summary>
<br>

Cada parte tiene su propia cadena de respaldo (detalles en [la guía de uso](docs/USO.md#cuando-algo-falla)):

```mermaid
flowchart TB
    subgraph VOZ["🔊 Voz de ARIA"]
        direction LR
        V1["Gemini «Leda»"] -- "falla" --> V2["Piper<br/>en tu máquina"]
        V2 -- "falla" --> V3["Voz del navegador"]
    end
    subgraph STT["📝 Transcripción de lo que dices"]
        direction LR
        T1["Groq Whisper"] -- "falla" --> T2["Whisper<br/>en tu máquina"]
    end
    subgraph VIS["📷 Visión de fotos"]
        direction LR
        F1["Gemini"] -- "falla" --> F2["Groq"]
    end
```

- La palabra «Aria» del modo manos libres se detecta en tu máquina (Vosk, contenedor `aria-voz`).
- El modelo local nunca se usa para imágenes.

</details>

<p align="right"><a href="#readme-top">⬆️ Volver arriba</a></p>

## 🔒 Seguridad y privacidad

- **Lo que sale de casa.** Con el cerebro local no sale nada. Con Ollama Cloud, Groq o Gemini, tus mensajes, parte de tu memoria y los resultados de las herramientas (estado de la máquina, anuncios bloqueados, nombres de dispositivos…) se envían a esas empresas. En el plan gratuito de Google, Google puede usarlos para mejorar sus productos. Si no quieres, desactiva esos cerebros en Ajustes → Cerebros.
- **Voz e imágenes.** El audio y las fotos se procesan en memoria y **no se guardan nunca**; solo queda el texto. Al hablar, el audio va a Groq (o se transcribe en tu máquina si no hay clave). Las fotos van a Gemini o Groq, sin metadatos (GPS, cámara…).
- **Acceso.** HTTPS siempre, contraseñas cifradas (scrypt), 5 intentos fallidos bloquean la IP 5 minutos, protección CSRF y permisos por rol comprobados en el servidor. **Verificación en dos pasos** opcional (TOTP) por usuario, con el secreto cifrado y códigos de recuperación de un solo uso.
- **Calendario suscrito.** El enlace `/cal/<token>.ics` no necesita sesión: el token es largo, aleatorio y revocable (ARIA solo guarda su huella). No lo compartas; si se filtra, crea uno nuevo en Agenda → Sincronizar.
- **Secretos.** `.env` y `data/` no se suben a git. Las claves de las IA nunca se muestran en la web. Las claves privadas de WireGuard solo llegan al navegador cuando descargas un `.conf`.
- **Escaneo defensivo.** El agente Seguridad solo escanea la red de `ARIA_RED_PERMITIDA`, nunca ataca ni prueba contraseñas.
- **Módulos.** Son código con los mismos permisos que ARIA: instala solo los de confianza.
- **Copias.** Las copias contienen secretos: guárdalas fuera de la máquina y cifradas (ver [copias diarias](docs/INSTALACION.md#13-copias-de-seguridad-diarias-y-cifradas)).

> [!CAUTION]
> Los botones «Copiar contraseña» de Inicio dan la contraseña de los paneles de SHIELD-DNS y HEIMDALL a los administradores. Protege bien tu contraseña de ARIA.

## 🐳 Contenedores y puertos

| Contenedor | Para qué | Puertos en tu máquina |
|---|---|---|
| `aria-caddy` | HTTPS y proxy | 80 (redirige a 443), 443 |
| `aria-app` | La aplicación | ninguno |
| `aria-ollama` | Modelo local y puente con Ollama Cloud | ninguno |
| `aria-searxng` | Búsqueda en internet | ninguno |
| `aria-voz` | Voz local (Whisper, Piper, Vosk), sin salida a internet | ninguno |
| `aria-escaner` | Escaneo de red (nmap) | ninguno |

Las otras aplicaciones usan: SHIELD-DNS 53, 8080 y 8443; HEIMDALL 51820/udp y 51843. Si las instalas en la misma máquina no hay choques.

Comandos útiles (desde la carpeta de ARIA):

```bash
./update.sh                 # actualizar
./backup.sh                 # copia de .env y data/ en backups/ (guarda las 7 últimas)
./uninstall.sh              # quitar contenedores (conserva datos)
docker compose ps           # estado
docker compose logs -f app  # registros
```

<p align="right"><a href="#readme-top">⬆️ Volver arriba</a></p>

## 🆘 Problemas frecuentes

Los más habituales. La lista completa está en la [guía de instalación](docs/INSTALACION.md#17-problemas-frecuentes).

<details>
<summary><b>«No puedo hablar con Docker» al instalar</b></summary>
<br>

Tu usuario aún no está en el grupo `docker`. Cierra sesión, vuelve a entrar y repite.
</details>

<details>
<summary><b>La página no carga</b></summary>
<br>

`docker compose ps` y `docker compose logs caddy app`. Comprueba que nada más usa los puertos 80 y 443:

```bash
sudo ss -tlnp | grep -E ':80 |:443 '
```
</details>

<details>
<summary><b><code>aria.local</code> no carga</b></summary>
<br>

Usa la IP (`https://192.168.1.50`). Algunos Android y Windows no resuelven `.local`.
</details>

<details>
<summary><b>Olvidé la contraseña de <code>admin</code></b></summary>
<br>

Si nunca la cambiaste en Ajustes, está en `.env` (`ARIA_PASSWORD`). Si la cambiaste, otro administrador puede ponerte una nueva en Ajustes → Usuarios.
</details>

<details>
<summary><b>Las respuestas tardan mucho</b></summary>
<br>

Estás usando el cerebro local. Añade una [clave gratuita](docs/INSTALACION.md#6-claves-gratuitas-de-ia-opcional) o mira Ajustes → Cerebros.
</details>

<details>
<summary><b>SHIELD-DNS o HEIMDALL salen «no conectado»</b></summary>
<br>

Revisa en el `.env` de ARIA que `SHIELD_URL` y `VPN_URL` llevan la IP de tu máquina ([paso 7](docs/INSTALACION.md#7-ajusta-aria-a-tu-red)) y que están sus contraseñas (`SHIELD_PASSWORD`, `VPN_USER`, `VPN_PASSWORD`). Si las apps están en `~/homelab`, repite `./install.sh` y copia las contraseñas solo.
</details>

<details>
<summary><b>El micrófono no funciona</b></summary>
<br>

Hace falta HTTPS y dar permiso al navegador. Instala el certificado ([paso 8](docs/INSTALACION.md#8-entrar-desde-casa-sin-avisos-de-certificado)) y revisa el permiso del micrófono del sitio.
</details>

<details>
<summary><b>Recibo «No se puede entrar en ARIA desde fuera» sin tener dominio</b></summary>
<br>

Deja vacía `ARIA_URL_PUBLICA` en `.env` y `docker compose up -d`.
</details>

## 🛠️ Para desarrolladores

- Código en `app/aria/` (FastAPI), web sin paso de compilación en `app/static/`, pruebas en `app/tests/`.
- **Demo con datos inventados** para probar la interfaz y regenerar las capturas: [herramientas/demo](herramientas/demo/README.md) (`arrancar.sh --sembrar` y `capturar.py docs/img`).
- Notas para agentes de programación: [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md), [SKILLS.md](SKILLS.md) y decisiones técnicas en [MEMORY.md](MEMORY.md).
- Pruebas:
  ```bash
  docker run --rm -v "$PWD/app:/srv" -w /srv python:3.12-slim sh -c "pip install -q -r requirements.txt pytest && python -m pytest -q"
  node app/tests/md.test.js
  ```

## 🗺️ Hoja de ruta

Ideas de nuevas aplicaciones (Home Assistant, Jellyfin, gasolineras…) y mejoras del núcleo en **[docs/PLAN.md](docs/PLAN.md)**. La mayoría se pueden hacer como módulos.

## 🌐 El ecosistema ARIA

| | Proyecto | Qué hace | Puertos |
|:---:|---|---|---|
| 🤖 | **ARIA** (este repositorio) | Asistente de IA y panel central de la casa | 80, 443 |
| 🛡️ | [SHIELD-DNS](https://github.com/BertMarti/SHIELD-DNS) | Bloqueador de anuncios para toda la casa (Pi-hole v6 + Unbound) | 53, 8080, 8443 |
| 🔐 | [HEIMDALL](https://github.com/BertMarti/HEIMDALL) | VPN WireGuard para entrar en casa desde fuera (wg-easy + Caddy) | 51820/udp, 51843 |

```mermaid
flowchart LR
    ARIA["🤖 ARIA"] -- "estadísticas, pausa,<br/>inventario y control parental" --> SD["🛡️ SHIELD-DNS"]
    ARIA -- "dispositivos, QR<br/>y avisos de conexión" --> HD["🔐 HEIMDALL"]
    HD -- "DNS de la VPN:<br/>sin anuncios fuera de casa" --> SD
```

## 📄 Licencia

MIT. Consulta [LICENSE](LICENSE).

<p align="right"><a href="#readme-top">⬆️ Volver arriba</a></p>
