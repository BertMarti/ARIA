<p align="center">
  <sub>Parte del ecosistema ARIA&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/ARIA">🤖 ARIA</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/SHIELD-DNS">🛡️ SHIELD-DNS</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/HEIMDALL">🔐 HEIMDALL</a></sub>
  <br>
  <a href="../README.md">🏠 README</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="INSTALACION.md">📘 Instalación</a>&nbsp;&nbsp;·&nbsp;&nbsp;<b>🧭 Uso</b>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="MODULOS.md">🧩 Módulos</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="PLAN.md">🗺️ Hoja de ruta</a>
</p>

# Guía de uso

Esta guía explica qué hay en cada parte de ARIA y cómo sacarle partido en el día a día. Si aún no la has instalado, empieza por la [guía de instalación](INSTALACION.md).

## Índice

1. [Un vistazo rápido](#un-vistazo-rápido)
2. [Inicio](#inicio)
3. [Compartir](#compartir)
4. [Enviar a la tele](#enviar-a-la-tele)
5. [Chat](#chat)
6. [Agentes especializados](#agentes-especializados)
7. [Voz](#voz)
8. [Imágenes y tickets](#imágenes-y-tickets)
9. [Memoria y diario](#memoria-y-diario)
10. [Notas](#notas)
11. [Tus documentos](#tus-documentos)
12. [Listas](#listas)
13. [Resumen diario](#resumen-diario)
14. [Propuestas de ARIA](#propuestas-de-aria)
15. [Recordatorios](#recordatorios)
16. [Rutinas](#rutinas)
17. [Finanzas](#finanzas)
18. [Red](#red)
19. [Control parental](#control-parental)
20. [Seguridad](#seguridad)
21. [Centro de control](#centro-de-control)
22. [Cerebro](#cerebro)
23. [Modo HUD](#modo-hud)
24. [Agenda y cumpleaños](#agenda-y-cumpleaños)
25. [Mapa](#mapa)
26. [Información e inversiones](#información-e-inversiones)
27. [Precio de la luz](#precio-de-la-luz)
28. [Ajustes](#ajustes)
29. [Avisos](#avisos)
30. [Telegram](#telegram)
31. [Notificaciones push](#notificaciones-push)
32. [Atajos: Ctrl+K y Compartir](#atajos-ctrlk-y-compartir)
33. [Acceso por invitación](#acceso-por-invitación)
34. [Usuarios y roles](#usuarios-y-roles)
35. [Cuando algo falla](#cuando-algo-falla)

## Un vistazo rápido

La barra de navegación tiene estas secciones:

| Sección | Para qué | Quién la ve |
|---|---|---|
| **Inicio** | Resumen del día, tus aplicaciones y acciones rápidas | Todos |
| **Chat** | Hablar con ARIA | Todos |
| **Finanzas** | Tus gastos, ingresos y presupuestos | Todos (cada uno los suyos) |
| **Información** | Noticias por temas y tus inversiones | Todos |
| **Agenda** | Calendario, eventos y cumpleaños | Todos (cada uno los suyos) |
| **Mapa** | Buscar lugares, rutas y sitios cercanos | Todos |
| **Red** | Dispositivos de casa, velocidad y control parental | Administradores |
| **Seguridad** | Escaneo defensivo de la red | Administradores |
| **Control** | Centro de control de SHIELD-DNS, HEIMDALL y el sistema | Administradores |
| **Ajustes** | Voz, memoria, avisos, rutinas, usuarios, módulos… | Todos (con más opciones para administradores) |

Arriba a la derecha está la **campana** de avisos.

## Inicio

Es la página que ves al entrar.

- **«Pregúntale a ARIA»**: escribe (o pulsa el micrófono) y se abre un chat con tu pregunta.
- **Tu ARIA, en tarjetas numeradas**: *01 Modo HUD*, *02 Resumen del día*, *03 Agenda*, *04 Tu casa* (solo administradores), *05 Información*, *06 Mapa*, *07 Chat* y *08 Finanzas*. Cada tarjeta enseña un dato vivo (el tiempo y la luz, tu próxima cita, los dispositivos de casa y los anuncios atrapados, tus inversiones, lo gastado este mes…) y su estado: **ACTIVO**, **AVISO** si hay algo que mirar o **PRONTO** para lo que está en construcción. Al pulsar una, vas a esa sección; *Resumen del día* te lleva al resumen (y lo vuelve a abrir si lo cerraste).
- **Resumen del día**: tarjetas con el tiempo, tus aplicaciones, la red, tus finanzas, tus inversiones y tu agenda de hoy (ver [Resumen diario](#resumen-diario)). **▶ Escuchar** lo lee ARIA en un minuto ([briefing hablado](#briefing-hablado)); también puedes cerrarlo por hoy o actualizarlo.
- **Aplicaciones**: un mosaico por aplicación (Chat, SHIELD-DNS, HEIMDALL y los [módulos](MODULOS.md) que tengas). El punto de color dice si está **activa**, **caída** o **sin instalar**. Al pulsar, se abre en una pestaña nueva. En SHIELD-DNS y HEIMDALL, **Copiar contraseña** te ahorra teclearla en su panel (solo administradores).
- **Acciones rápidas** (administradores): *Pausar anuncios 5 min*, *Reanudar anuncios*, *Añadir dispositivo a la VPN* y *Estado del sistema*.
- **Sistema**: temperatura, memoria, disco y carga de la máquina.

## Compartir

En **Compartir** tienes un reproductor local, con controles inspirados en VLC, para ver o escuchar archivos desde el navegador.

- Pulsa **Abrir carpeta** o **Abrir archivos**, o arrastra archivos y carpetas a la zona de carga. Puedes añadir varias carpetas y archivos en varias tandas; se ordenan por carpeta y por capítulo con orden natural y no se duplican.
- Los archivos **no se suben**: se leen dentro del navegador. La Raspberry no guarda una copia.
- Los subtítulos `.srt` y `.vtt` con el mismo nombre que el vídeo se activan automáticamente. Con **V** puedes cambiar de pista o quitarlos.
- **Seguir viendo** reanuda los vídeos donde los dejaste. En Chrome y Edge, la lista de carpetas y archivos se puede recuperar al recargar si concedes permiso de lectura.
- El volumen llega hasta el **200 %**. También hay velocidad, repetición, aleatorio, aspecto, bucle A-B, captura e información del archivo.
- Pulsa **Pantalla completa** o **F**. En pantalla completa, los controles se superponen y se ocultan cuando no mueves el ratón; vuelven al moverlo.
- Pulsa **?** para ver la lista completa de atajos de VLC: pausa, saltos de 10 segundos, velocidad, subtítulos, volumen, posición, captura y más.

Los navegadores que no permiten recuperar carpetas siguen recordando la posición, pero tendrás que abrir de nuevo los archivos después de recargar.

## Enviar a la tele

Desde **Compartir**, reproduce un archivo y pulsa **Enviar a la tele**. ARIA descubre dispositivos Google Cast/Chromecast/Google TV y DLNA en tu red; también puedes añadir un dispositivo por IP.

- **Google Cast** funciona como Chrome, incluidas teles, Chromecast, Google TV, altavoces y grupos compatibles.
- **DLNA** funciona con muchos modelos de Samsung, LG, Sony y otras marcas.
- Para **Apple TV** o **Fire TV**, abre el enlace con VLC o cópialo desde «¿Apple TV o Fire TV?».
- La Raspberry hace de puente en vivo: la tele pide el vídeo a `http://192.168.1.50:8095/flujo/<token>/...` y ARIA se lo pide al navegador que tiene el archivo. No se guarda nada en la Raspberry.
- Mantén abierta la pestaña de **Compartir** mientras ves el vídeo. Si la cierras, el canal se corta.
- El enlace es temporal: el token se invalida al cerrar la pestaña y caduca como máximo a las 12 horas. El puerto `8095` solo está disponible en la red local.

Desde el panel puedes reproducir, pausar, detener y saltar 10 segundos. La posición inicial se conserva al enviarlo.

## Chat

- Escribe abajo y pulsa **Enviar**. La respuesta llega en directo; **Detener** la corta.
- A la izquierda (en el móvil, con el botón ☰) están tus conversaciones: **+ Nueva**, renombrar y borrar.
- Cada respuesta lleva insignias con el **cerebro** que la dio (Ollama Cloud, Groq, Gemini o local) y el **agente**.
- En la cabecera eliges el **agente** de la conversación (o «ARIA (automático)»).
- Junto a la caja de texto tienes el **micrófono**, **Manos libres** y el botón de **imagen**.
- **¿Qué ves?**: en el chat o el HUD, pulsa el botón de cámara (o di «**Aria, ¿qué ves?**» o «**léeme esto**» en manos libres). Se abre una vista previa, haces la foto y la cámara se apaga. ARIA analiza la imagen y te responde. Útil para identificar objetos, leer textos difíciles o transcribir facturas.
- **Copiar** copia un mensaje; **Leer** lo lee en voz alta.

### Frases de ejemplo

| Tema | Prueba a decir |
|---|---|
| Casa | «¿Cuántos anuncios has bloqueado hoy?» · «Pausa el bloqueador 10 minutos» · «¿Qué temperatura tiene la Raspberry?» |
| VPN | «¿Qué dispositivos hay en la VPN?» · «Añade un dispositivo a la VPN llamado movil-ana» · «Desactiva el portátil de Lucía» |
| Internet | «¿Qué noticias hay hoy de tecnología?» · «Busca el horario del museo del Prado» |
| Enlaces | Pega un enlace y escribe «resúmelo» |
| Tiempo | «¿Qué tiempo hace en Madrid?» |
| Recordatorios | «Recuérdame mañana a las 9 llamar al taller» |
| Rutinas | «Crea una rutina que de lunes a viernes a las 7:30 me diga el tiempo» |
| Memoria | «Recuerda que mi equipo es el Atlético» · «Olvida lo del equipo» |
| Finanzas | «Apunta 12,50 € en el supermercado» · «¿Cuánto llevo gastado este mes?» |
| Red | «¿Hay dispositivos nuevos en la red?» · «Haz un test de velocidad» |
| Módulos | «¿Responde example.org?» (módulo *uptime*) |

Por seguridad, **borrar dispositivos de la VPN solo se puede hacer desde la interfaz**, con confirmación: el chat no puede.

## Agentes especializados

Además de ARIA (general), hay tres agentes con su propio oficio:

| Agente | Para qué | Quién |
|---|---|---|
| **ARIA** | Charla, la casa, la VPN, el bloqueador, búsquedas… | Todos |
| **@finanzas** | Gastos, ingresos, categorías y presupuestos (siempre los tuyos) | Todos |
| **@redes** | Dispositivos de la LAN, latencia, velocidad, DNS, VPN y control parental | Administradores (un usuario solo consulta la salud de la red) |
| **@seguridad** | Informe defensivo: puertos, servicios de riesgo, vulnerabilidades | Solo administradores |

Cómo elegir:

- **Automático**: con «ARIA (automático)», ARIA decide según lo que escribas.
- **En la cabecera del chat**: el agente queda fijado para esa conversación.
- **Con un prefijo**, solo para un mensaje: `@finanzas ¿cuánto llevo en restaurantes?`, `@redes ¿qué dispositivos están pausados?`, `@seguridad haz un informe`, `@aria`.

## Voz

> El micrófono solo funciona por HTTPS y el navegador te pedirá permiso la primera vez.

- **Pulsar para hablar**: mantén pulsado el micrófono mientras hablas y suelta (o toca una vez para empezar y otra para terminar). Máximo 30 segundos. El texto se envía solo.
- **Leer**: el botón de cada respuesta la lee en voz alta. En **Ajustes → Voz** puedes hacer que lea todas las respuestas y cambiar la velocidad.
- **ARIA flotante**: pulsa el botón **Flotante** (o desde el HUD o con Ctrl+K) para abrir una pequeña ventana que siempre se mantiene encima de otras aplicaciones (Chrome/Edge escritorio). Incluye el orbe de estado, el texto de ARIA y acceso al micrófono. No cierres la pestaña principal de ARIA mientras la usas.
- **Lectura en streaming**: ARIA empieza a hablar en cuanto termina la primera frase. Funciona en el chat con «Leer respuestas», en manos libres y en el HUD. El resto del texto se agrupa en trozos grandes para no agotar la cuota de voz.
- **Manos libres**: pulsa **Manos libres** en el chat (o actívalo en Ajustes → Voz o con Ctrl+K). Aparece un aviso «escuchando "Aria"» con el botón **Dejar de escuchar**. Di «**Aria**» y tu pregunta («Aria, ¿qué hora es?»), o «Aria», una pausa corta y la pregunta. Suena un pitido, ARIA escucha hasta que te callas, responde y lo lee.
  - «Aria» solo cuenta al principio de una frase: «María» o «esta aria de ópera» no la activan.
  - El micrófono se apaga al cambiar de pestaña o bloquear el móvil.
- **Ajustes → Voz**: elegir micrófono y probarlo, leer en voz alta, manos libres y velocidad. Se guardan en cada dispositivo.

### Elegir la voz de ARIA

En **Ajustes → General → Voz**, apartado **Voz de ARIA**:

- **14 voces femeninas** de Google Gemini, cada una con su carácter (suave, amable, cálida, alegre…). Pulsa **▶** para escuchar una frase de muestra y **Elegir** para quedártela.
- **Tono**: *Dulce y cariñosa* (por defecto), *Alegre*, *Serena* o *Muy tierna*.
- **Acento**: *España* (por defecto) o *Latinoamérica*.
- **Escribe una frase** y pulsa **Escuchar** para oírla con tu elección.
- Para una voz dulce y amable se recomiendan **Achernar**, **Vindemiatrix**, **Sulafat**, **Despina** o **Leda** con el tono *Dulce y cariñosa* o *Muy tierna*.

La elección es de cada usuario y se usa en la web, el HUD y las notas de voz de Telegram. Las muestras se guardan, así que escuchar otra vez la misma combinación no gasta cuota. La capa gratuita de Gemini permite pocas voces por minuto y por día: si se agota, ARIA usa su voz local (femenina, española) hasta que se recupere.

### El escaparate y Ping

En `/hola` hay una página **pública** para enseñar ARIA a quien quieras sin darle acceso a nada: datos de ejemplo, voz pregrabada y ninguna llamada a tu ARIA. Activa **«Quiero escuchar a ARIA»** para que se presente; en mitad de la presentación, **Ping** (el hada de luz que vigila la red) la interrumpe con su «¡Eh, mira!». Ping sigue tu ratón unos segundos y después vuela por libre. Si usas Cloudflare Access, mira cómo abrir solo esa página en la [guía de instalación](INSTALACION.md).

Privacidad: para detectar «Aria», el sonido va a tu máquina (nunca fuera). Lo que dices después se transcribe con Groq (o en tu máquina si no hay clave). **El audio no se guarda nunca.**

## Imágenes y tickets

- En el chat, pulsa el botón de **imagen**, **pega** una captura (Ctrl+V) o **arrástrala**. Puedes añadir una pregunta o enviarla sin texto.
- El navegador reduce la foto y le quita los datos de ubicación antes de enviarla.
- **Tickets**: si la foto es un ticket, factura o recibo (o pides «apúntalo»), ARIA lee comercio, fecha, total y categoría y **te propone** apuntar el gasto con **Registrar gasto** / **Descartar**. Nada se apunta sin pulsar.
- La visión usa Gemini y, de respaldo, Groq. El modelo local no ve imágenes: sin esas claves, ARIA te lo dirá.
- Límite: 6 imágenes por minuto y 60 por hora por persona. **Las imágenes no se guardan**: en el historial queda «Imagen» y tu texto.

## Memoria y diario

- **Recuerdos**: «recuerda que soy alérgica al marisco», «olvida que…». También en **Ajustes → Memoria**, donde los ves, editas y borras. Cada persona tiene los suyos (hasta 200).
- **Aprendizaje automático** (interruptor en Ajustes → Memoria): tras cada mensaje, ARIA puede guardar hasta 3 datos duraderos sobre ti. Nunca guarda contraseñas, claves, tarjetas ni documentos de identidad. Solo lo hace con un cerebro de la nube.
- **Diario**: cada madrugada ARIA resume en unas viñetas lo que hiciste ese día. En Ajustes → Memoria ves los últimos 14 días y puedes borrar cualquiera.
- **«Borrar toda mi memoria»** elimina recuerdos y diario.

### Memoria semántica

ARIA elige qué recuerdos usar según su significado, no solo por coincidencia de palabras. Para esto usa un modelo que corre en tu propia máquina (Ollama con `granite-embedding`), por lo que no envía tus recuerdos fuera para buscarlos. Si este modelo no está disponible, utiliza el método de búsqueda tradicional.

### Fuente y confianza

En **Ajustes → Memoria** puedes ver el origen y la fiabilidad de cada dato:
- **Tú lo dijiste**: tiene una confianza del 100 % y nunca se borra solo.
- **Aprendizaje automático**: ARIA le asigna un 60 % de confianza inicial, que sube cada vez que se usa el recuerdo. Los datos aprendidos solos que no se utilicen en 90 días se olvidan automáticamente.

La memoria se envía a los cerebros de la nube junto con tus preguntas para darte contexto. Al cerebro local solo le llega un trozo pequeño.

## Notas

Para apuntar cosas sueltas: ideas, la lista de la compra o mejoras para ARIA. Están en la sección **Notas** de la web.

- **Telegram**: `/nota texto` apunta una nota; `/mejora texto` (administradores) apunta una mejora para ARIA; `/notas` te las lista.
- **Chat**: «apúntame comprar pilas», «anota estas ideas: …». Si escribes una lista con viñetas, cada línea se guarda como una nota.
- **Web**: escribe la nota, elige la categoría (**General**, **Mejoras**, **Ideas** o **Compra**) y pulsa **Añadir**. Puedes filtrar por categoría, marcarla como hecha, editarla o borrarla. **Ver hechas** muestra también las terminadas.
- Las **mejoras** de los administradores se copian solas a un plan privado de la máquina (sección «Notas y mejoras desde Telegram»), para tenerlas a mano al mejorar ARIA. No se publican en ningún sitio.
- Cada persona ve solo las suyas. Los invitados no tienen notas.

### Tus documentos

En **Notas → Documentos** puedes subir tus papeles y preguntarle a ARIA por su contenido.

- Se admiten archivos **PDF, TXT y MD** de hasta **15 MB**. Cada usuario dispone de una cuota de **300 MB** y **200 documentos**; además, hay un límite de 10 subidas por hora.
- Los PDF pueden tener hasta **400 páginas**. El texto se extrae en un proceso aislado, con límites de memoria, CPU, tiempo y salida, para reducir el riesgo de PDF maliciosos. Después se limpia, se divide en fragmentos y se indexa.
- La búsqueda prioriza el significado con el modelo local de embeddings de la Pi. Si no está disponible, usa coincidencias de palabras.
- En el chat, prueba «¿qué dice mi contrato sobre…?» o «según el manual…». ARIA usa `buscar_en_documentos` y cita cada fragmento como **[documento, pág. N]**.
- El archivo y el índice permanecen en la Pi. Al hacer una pregunta, los fragmentos relevantes se envían al cerebro que responde; si es un cerebro de la nube, esos fragmentos salen de casa.
- Solo el dueño puede ver, buscar, descargar y borrar sus documentos. Los invitados no tienen acceso.
- En **Ajustes → General → Mis datos** se exportan los metadatos de los documentos, no los archivos originales. Al borrar la cuenta se eliminan también sus archivos e índice.

## Listas

En la pestaña **Listas** de **Notas** puedes llevar la compra y otras listas de casa. Hay dos visibilidades:

- **De casa**: todos los usuarios pueden verlas y editarlas. Los invitados no tienen acceso a las listas.
- **Solo yo**: son privadas para su propietario; ni siquiera un administrador puede verlas o editarlas.

**La compra** se crea automáticamente como lista de casa cuando se usan las listas por primera vez. Puedes añadir varios artículos separados por comas o por «y» («leche, pan y huevos»); los artículos pendientes repetidos no se duplican. Marca artículos como hechos y usa **Vaciar hechos** para retirarlos.

También puedes gestionarlas desde el chat con `anadir_a_lista`, `ver_lista`, `marcar_en_lista` y `quitar_de_lista`. Si no indicas una lista, ARIA usa **La compra**. Por Telegram, `/compra <artículo>` añade artículos a La compra y `/lista` muestra sus pendientes; `/lista <nombre>` muestra otra lista.

El resumen diario incluye una línea como **🛒 La compra: N cosas pendientes**. En **Ajustes → General → Mis datos**, el ZIP incluye tus listas propias y los artículos que has añadido en `listas.json`.

## Resumen diario

Un único resumen que verás igual en tres sitios: la tarjeta **Resumen del día** de Inicio, el panel del **HUD** y un mensaje de **Telegram** bien maquetado (negritas, secciones y emojis).

| Sección | Qué cuenta | Quién la ve |
|---|---|---|
| 🌤️ El tiempo | Cielo, temperatura ahora, mínima, máxima y lluvia; avisa si mañana cambia mucho | Todos (si pusiste `ARIA_CIUDAD`) |
| ⚡ Precio de la luz | Media, precio de ahora, hora más barata y más cara y mejores horas que quedan | Todos (si `ARIA_LUZ=1`) |
| 📊 Tus aplicaciones | «Todo en orden» o la lista de cosas que revisar: SHIELD-DNS, HEIMDALL, cerebros de IA, Raspberry (temperatura, RAM, disco) y copia | Administradores |
| 🛜 Red | Dispositivos nuevos en 24 h y los que siguen sin identificar | Administradores |
| 💶 Finanzas | Lo gastado este mes frente al mes pasado **a estas alturas**, ingresos y presupuestos | Cada uno los suyos |
| 📈 Mis inversiones | Precio en euros y variación del día de tu lista de seguimiento | Cada uno la suya |
| 📅 Hoy | Eventos, recordatorios y cumpleaños de la semana | Cada uno los suyos |
| 🛒 La compra | Número de artículos pendientes de la lista de casa | Todos los usuarios |
| 🩺 Salud del sistema | Disponibilidad de los servicios e incidentes recientes dentro de «Tus aplicaciones» | Administradores |

- Por **Telegram** o **notificación** a la hora que elijas (por defecto, las 08:00): actívalo en **Ajustes → Avisos**. En Telegram llega con botones: **Abrir ARIA**, **Agenda**, **Actualizar** y, para administradores, **Pausar anuncios 30 min**. También puedes pedirlo cuando quieras con `/resumen` o diciéndole «resúmeme el día».
- El resumen se prepara una vez cada 10 minutos como mucho; **Actualizar** lo rehace al momento.

### Briefing hablado

El resumen del día, **contado por ARIA en un minuto** y con la voz que elegiste: el tiempo, las horas de luz más baratas, tu agenda en orden, los cumpleaños de hoy, cómo está la casa, tus gastos del mes y lo que más se mueve en tus inversiones.

- **Telegram**: debajo del resumen de la mañana llega como **nota de voz**. Puedes quitarlo en **Ajustes → Avisos** («En Telegram, también con la voz de ARIA»). Y en cualquier resumen, el botón **🔊 Escuchar** te lo manda al momento.
- **HUD**: acción rápida **Briefing del día**, con el texto en subtítulos.
- **Inicio**: **▶ Escuchar** en la tarjeta del resumen (y **■ Parar**).
- Se prepara una vez por la mañana, otra por la tarde y otra por la noche, y se guarda: escucharlo otra vez no gasta cuota de voz. Si la cuota de Gemini está agotada, lo lee la voz local y se vuelve a intentar con tu voz más tarde.

## Propuestas de ARIA

ARIA puede sugerir acciones útiles, pero nunca las realiza sin tu aprobación explícita («Sí, hazlo»). Las propuestas aparecen en **Inicio** y en **Telegram** con botones para aceptar o rechazar.

- **Qué propone**: recordatorios para la hora más barata de la luz (por la mañana), avisos 30 minutos antes de una cita que empiece pronto (en 1 a 3 horas) y, solo para administradores, marcar como conocido un dispositivo nuevo que aún no está identificado en la red.
- **Funcionamiento**: las propuestas caducan solas si no las atiendes. Nunca verás más de 10 pendientes.
- **Invitados**: los usuarios con acceso por invitación no reciben propuestas.
- **Desactivar**: se pueden apagar por completo con `ARIA_PROPUESTAS=0` en el archivo `.env`.

## Recordatorios

Pídeselos a ARIA en el chat o por Telegram:

- «Recuérdame mañana a las 9 llamar al taller»
- «Avísame en 20 minutos»
- «Todos los lunes a las 8 sacar la basura» (también diarios o de lunes a viernes)
- «¿Qué recordatorios tengo?» · «Borra el recordatorio 3»

También se ven y se crean en **Ajustes → Recordatorios**. Llegan por la campana, Telegram y notificación, incluso en horas de silencio.

## Rutinas

Una rutina es una pregunta que ARIA se hace sola a una hora y te manda la respuesta. Por ejemplo: «cada mañana a las 8, dime el tiempo en Madrid y 3 titulares de tecnología».

- **Dónde**: **Ajustes → Rutinas** (crear, editar, pausar, borrar y **Ejecutar ahora**), en el chat («crea una rutina…», «¿qué rutinas tengo?», «borra la rutina del tiempo»), en Telegram con `/rutinas` y con **Ctrl+K**.
- **Cuándo**: todos los días a una hora, ciertos días («los lunes y jueves a las 9», «de lunes a viernes», «los fines de semana») o cada N horas (mínimo cada hora).
- **Entrega**: Telegram, notificación, ambos o solo la campana. El resultado completo queda en la conversación «Rutina · nombre».
- **Solo consultan**: una rutina puede mirar el tiempo, noticias, el estado de la casa o tus finanzas, pero nunca cambia nada (no pausa el bloqueador, no toca la VPN, no apunta gastos…).
- Necesitan un **cerebro de la nube**: si solo responde el local, la rutina se salta y te deja una nota.
- Límite: 10 rutinas por persona.

## Finanzas

Tus cuentas personales. Cada usuario solo ve las suyas. ARIA **no se conecta a ningún banco** ni da consejos de inversión.

- **Resumen del mes** y **Gastos por categoría**.
- **Presupuestos mensuales** por categoría, con su barra de progreso.
- **Apuntar movimiento**: fecha, concepto, importe (negativo = gasto) y categoría. O desde el chat: «apunta 30 € de gasolina».
- **Movimientos**: buscar, filtrar por mes y categoría, editar. Al editar puedes marcar «aplicar a movimientos parecidos» y se crea una regla.
- **Importar extracto CSV**:
  1. Descarga los movimientos de tu banco en CSV (si solo da Excel, ábrelo y guárdalo como CSV).
  2. Pulsa **Importar extracto CSV** y elige el archivo (máximo 2 MB).
  3. ARIA detecta el formato. Revisa qué columna es la fecha, el concepto y el importe, y mira la vista previa.
  4. Pulsa **Importar**. Lo que ya estaba no se duplica.
- **Sugerir categorías (nube)**: opcional. Envía solo los conceptos sin categoría (sin importes ni fechas) a un cerebro de la nube. Nada se aplica hasta que aceptas cada sugerencia.

## Red

Solo para administradores. Necesita SHIELD-DNS para ver los dispositivos.

- **Salud**: latencia al router y a internet, DNS, VPN y la última velocidad.
- **Medir latencia** y **Test de velocidad** (descarga ~15 MB y sube ~5 MB; uno cada 10 minutos).
- **Historial (7 días)**: gráfica de las mediciones.
- **Dispositivos de la LAN**: nombre, IP, fabricante, MAC, puertos y cuándo se vio. Lo desconocido aparece resaltado. Ponle un alias o márcalo como conocido (o **Marcar todos como conocidos** la primera vez). En el **móvil**, cada dispositivo se ve como una ficha con sus datos en dos columnas.
- **Estadísticas por dispositivo**: consultas y porcentaje de bloqueo de cada uno en 24 horas o 7 días; pulsa uno para ver su detalle. Si SHIELD-DNS no responde, lo dice claramente y vuelven solas cuando se recupera.

<p align="center"><img alt="Red en el móvil" src="img/captura-movil-red.png" width="260"></p>
- Botón **Control** de cada dispositivo: el [control parental](#control-parental).

## Control parental

Por dispositivo, desde **Red → Control**, desde el agente **@redes** o con `/control` en Telegram. Solo administradores.

- **Pausar internet**: 30 min, 1 h, 2 h, 4 h o hasta que lo reanudes.
- **Bloquear servicios**: TikTok, YouTube, Instagram, Facebook, WhatsApp, Snapchat, X, Twitch, Discord, Fortnite/Epic, Roblox, Minecraft, Steam, Netflix, Disney+ y Prime Video.
- **Horarios**: «sin internet de 23:00 a 08:00 de lunes a viernes» o «sin TikTok de 16:00 a 20:00».
- Frases para @redes: «pausa la tablet de Lucía una hora», «bloquea TikTok en el móvil de Ana», «¿qué dispositivos están pausados?».

Siempre actúa sobre **un** dispositivo concreto: no hay «pausar a todos». El router, la propia máquina de ARIA y las IP de `ARIA_CONTROL_PROTEGIDOS` nunca se pueden pausar.

> **Límite importante: es un bloqueo por DNS.** Funciona porque el dispositivo pregunta a SHIELD-DNS por cada web. No frena a un dispositivo que:
> - tenga un DNS fijo distinto (por ejemplo `8.8.8.8`);
> - use DNS cifrado (DoH/DoT, el «DNS privado» de Android, iCloud Private Relay);
> - use una VPN;
> - use el DNS secundario del router, si pusiste uno externo.
>
> Además, el dispositivo puede tardar unos minutos en notar el cambio. Para un corte total, bloquea el dispositivo en el router.

## Seguridad

Solo para administradores. Un escaneo **defensivo** de tu red de casa:

- **Escanear ahora (100 puertos)** o **Escaneo completo (1000 puertos)**. Como mucho uno cada 10 minutos, y uno automático cada domingo de madrugada.
- **Resumen** y **Hallazgos** con gravedad (alta, media, baja): servicios de riesgo abiertos (Telnet, SMB, escritorio remoto, VNC, UPnP, bases de datos…), paneles web sin HTTPS, puertos nuevos, dispositivos sin reconocer, versiones con vulnerabilidades conocidas y dispositivos VPN que no se usan.
- **Lo más bloqueado por dispositivo** (Pi-hole, últimas 24 h).
- O pregunta a `@seguridad`: «¿hay algo peligroso en mi red?».

Cada hallazgo incluye **Cómo arreglarlo**, con pasos guiados y las acciones que correspondan: **Es mío**, **Marcar como revisado**, **Desactivar peer**, **Aceptar riesgo** indicando el motivo y durante 30, 90 o 365 días, y **Ya está, compruébalo**, que vuelve a escanear ese punto. **Arreglar lo que ARIA puede** reúne las acciones seguras que ARIA sí puede aplicar. Los hallazgos apartados aparecen en **Aceptados y revisados**, donde puedes reabrirlos.

ARIA no modifica el sistema ni el router. Cuando una solución requiere cambiar una configuración, la interfaz solo te guía con los pasos.

Qué **no** hace: no ataca, no prueba contraseñas, no explota fallos y no escanea fuera de `ARIA_RED_PERMITIDA`. Tampoco mira tu casa desde internet: revisa en el router que solo esté abierto el puerto de la VPN (51820/UDP) y que la gestión remota esté desactivada.

## Centro de control

Solo para administradores. Tarjetas que se actualizan solas cada 15 segundos:

- **SHIELD-DNS**: consultas, bloqueos y porcentaje. **Pausar 5/30/60 min** y **Reanudar**.
- **HEIMDALL**: dispositivos de la VPN y cuáles están conectados.
  - **Añadir dispositivo**: escribe un nombre, pulsa **Crear** y escanea el QR con la app WireGuard del móvil (o **Descargar .conf** para un ordenador).
  - **QR** vuelve a mostrar el código; **Activar/Desactivar** corta o devuelve el acceso; **Eliminar** pide confirmación.
- **Sistema**: temperatura, memoria, disco, carga y tiempo encendida.
- **Sistema en directo**: CPU, memoria y red de cada contenedor, actualizado cada pocos segundos (necesita el pequeño agente del sistema, ver [INSTALACION.md](INSTALACION.md)).
- **Salud de los últimos días**: histórico de disponibilidad de ARIA, SHIELD-DNS, HEIMDALL, túnel, Ollama local, cerebros de la nube, búsqueda, voz, escáner, copias e internet. Hay un sondeo por minuto durante 30 días y agregados por hora durante un año. Puedes consultar 24 horas, 7 días o 30 días; muestra el porcentaje de cada servicio, sus caídas, la más larga y los incidentes. Solo la ven los administradores.
- **Reiniciar la Raspberry**: pide confirmación y deja una petición firmada que el agente del sistema comprueba antes de reiniciar. También desde Telegram.

Si una aplicación sale «no conectado», revisa su contraseña en `.env` (ver [Problemas frecuentes](INSTALACION.md#17-problemas-frecuentes)).

## Cerebro

Solo administradores. Muestra ARIA como una **red de nodos en 3D**, en vivo:

- Arriba, los **cerebros de IA**; en el centro, el **núcleo** con los **agentes** y sus familias de **herramientas**; abajo, los **servicios** (contenedores); a los lados, los **módulos**, los **canales** (web, Telegram, notificaciones) y los **datos** (base de datos, memoria, notas). También el túnel y las copias.
- Cada tipo tiene su color y un **anillo** que dice su estado: verde (bien), ámbar (aviso), rojo (falla) o gris (apagado).
- Cada vez que ARIA usa una herramienta, un **pulso de luz** recorre la red (verde si fue bien, rosa si falló). Arriba ves cuántas acciones hubo en el último minuto.
- El **núcleo ARIA** es un orbe de energía con anillos orbitales; de él sale cada pocos segundos una onda que recorre los enlaces. Los grupos principales llevan rótulo y el resto lo muestra al pasar el ratón.
- **Arrastra** para girar, usa la **rueda** (o pellizca) para acercar, **doble clic** para volver a la vista inicial y **clic** en un nodo para ver sus datos. Con el teclado: flechas para girar y +/− para acercar.
- Al pulsar un nodo, la vista se centra en él y el panel explica **qué hace**, su estado, sus datos, cómo mejorarlo y sus **conexiones**. Puedes pulsar una conexión en el panel para pasar a ese nodo.

## Modo HUD

Abre `https://aria.local/#hud` (o el mosaico **Modo HUD** de Inicio). Es una pantalla pensada para un monitor, una tableta o una tele.

<p align="center"><img alt="Modo HUD con tarjetas y orbe" src="img/captura-hud.png" width="100%"></p>

- **El orbe**, en el centro, respira en reposo y cambia de color cuando ARIA **escucha** (verde), **procesa** (violeta) y **habla** (ondulando al ritmo de su voz). Su brillo «mira» hacia el ratón y las partículas se apartan del cursor. Debajo salen los subtítulos.
- **Tarjetas** (cada una con su número y un piloto verde o ámbar): **clima**, **agenda de hoy**, **pendiente** (avisos y recordatorios), **finanzas**, **estado de la casa** (anillos de CPU, RAM y temperatura y la CPU del último minuto), **red y seguridad**, **precio de la luz** y **mercados**. Las de la casa y la red solo las ven los administradores. Al pasar el ratón por encima se iluminan y se inclinan en 3D.
- **Acciones rápidas** bajo el orbe: **Leer resumen** (ARIA te lo dice en voz alta), **Silenciar**, **Agenda** y, para administradores, **Pausar anuncios 30 min**.
- Abajo: escribe, mantén pulsado el micrófono o activa **Manos libres** y di «Aria».

### Opciones del HUD

Pulsa **Opciones** (arriba a la derecha). Todo se guarda en ese navegador.

<p align="center"><img alt="Panel de opciones del HUD" src="img/captura-hud-opciones.png" width="100%"></p>

| Opción | Qué hace |
|---|---|
| **Tarjetas** | Elige cuáles se muestran |
| **Color** | Cian, violeta, ámbar, verde o rosa: cambia tarjetas, fondo y orbe |
| **Movimiento con el ratón** | Parallax de la escena e inclinación de las tarjetas |
| **Fondo animado** | Rejilla en perspectiva y estrellas |
| **Cursor luminoso** | Un anillo de luz sigue al ratón |
| **Reloj con segundos** | Muestra también los segundos |
| **Gestos con la mano** | Controla el HUD moviendo la mano ante la cámara (palma = cursor, pellizco = clic, puño = agarrar, pulgar arriba = briefing). El vídeo no sale del navegador. |
| **Leer en voz alta las respuestas** | Lo que respondes desde el HUD se lee con la voz de ARIA |
| **Mantener la pantalla encendida** | Evita que la tableta se apague mientras el HUD está abierto |
| **Modo quiosco** | Al tocar la pantalla pasa a pantalla completa y los botones se esconden tras unos segundos sin uso |

Si tu sistema tiene activado «reducir movimiento» o usas una pantalla táctil, los efectos se desactivan solos.

> [!TIP]
> **Tableta en el salón**: abre el HUD, activa *Mantener la pantalla encendida* y *Modo quiosco*, y añade ARIA a la pantalla de inicio (app instalable). Toca una vez para pasar a pantalla completa.

## Agenda y cumpleaños

<p align="center"><img alt="Agenda con calendario mensual" src="img/captura-agenda.png" width="100%"></p>

- **Mes**, **Semana** o **Lista** (próximos 60 días). Pulsa un día para ver sus planes en el panel lateral; doble clic para crear un evento ese día.
- **+ Evento**: título, fecha, hora de inicio y fin (o **todo el día**), lugar, repetición (semanal, mensual o anual), aviso previo y notas. Pulsa un evento para **editarlo** o **borrarlo**; si se repite, el cambio se aplica a toda la serie.
- **+ Cumpleaños**: nombre, día, mes y, si quieres, el año para saber cuántos cumple. ARIA te avisa el mismo día o con antelación.
- Por chat: «apúntame el dentista el jueves a las 17:30», «¿qué tengo mañana?», «el cumpleaños de Lucía es el 11 de octubre».

### Ver la agenda en el móvil (Sincronizar)

Pulsa **Sincronizar**:

- **Suscribirte** (se actualiza sola): pulsa **Crear enlace**, cópialo y añádelo como *calendario suscrito*:
  - **iPhone / Mac**: botón «Abrir en iPhone/Mac», o Ajustes → Calendario → Cuentas → Añadir cuenta → Otra → *Añadir calendario suscrito*.
  - **Android**: en [calendar.google.com](https://calendar.google.com) desde el ordenador → *Otros calendarios* → «+» → *Desde URL*. Aparecerá en el móvil.
  - **Outlook**: *Agregar calendario* → *Suscribirse desde la web*.
- **Descargar .ics**: una copia para importar una vez (no se actualiza).

> [!IMPORTANT]
> El enlace es **privado**: quien lo tenga puede ver tu agenda (solo verla). ARIA lo enseña una sola vez; si lo pierdes o se filtra, crea uno nuevo (el anterior deja de funcionar) o pulsa **Desactivar**. Para que funcione fuera de casa, ARIA debe ser accesible desde internet; con Cloudflare Access añade una regla *Bypass* para la ruta `/cal/` (ver [INSTALACION.md](INSTALACION.md)).

## Mapa

Mapa de **OpenStreetMap**, sin claves ni seguimiento: busca una dirección, pulsa **Mi ubicación** (el navegador te pedirá permiso), traza una **ruta** o busca **farmacias, gasolineras, supermercados, restaurantes o cajeros** cerca.

### Mapa 3D

Pulsa **3D** junto a los botones del mapa (ARIA lo recuerda en cada dispositivo):

- **Edificios en 3D** al acercarte a una ciudad. Con todo el país a la vista el mapa está plano; al acercarte se inclina.
- **Inclinar y girar**: con dos dedos o con el botón derecho del ratón. **Vista cenital** lo vuelve a poner plano.
- **Vuela a…**: al buscar un sitio, el mapa vuela hasta él. Las búsquedas y **Cerca de** ponen un marcador por resultado; al pulsarlo ves su nombre (también en 2D).
- Los mapas 3D son de **OpenFreeMap**, gratis y sin claves. Si tu navegador no puede mostrar el 3D, ARIA vuelve sola al mapa 2D.

## Información e inversiones

<p align="center"><img alt="Información: inversiones y noticias" src="img/captura-informacion.png" width="100%"></p>

- **Noticias por temas** (España, Tecnología, Economía… los eliges en **Editar temas y seguimiento**). Arriba, **En resumen**: unas viñetas escritas por ARIA. Debajo, una ficha por noticia con el medio, la fecha y un extracto; púlsala para abrirla.
- **Mis inversiones**: busca un valor por nombre o símbolo (acciones, fondos, ETF, índices o criptomonedas) y añádelo. Si indicas **cantidad** y **precio medio**, verás el valor de tu posición y la ganancia o pérdida. Todo se convierte a **euros**, con una gráfica y la variación del día, la semana, el mes y el año (también Bitcoin y Ethereum).
- ARIA informa, **no aconseja**: no es un asesor financiero.

## Precio de la luz

Si vives en España, ARIA consulta cada día el precio de la tarifa regulada (**PVPC**) en la web pública de Red Eléctrica (sin claves):

- En **Inicio** y en el **HUD**: el precio de ahora, un gráfico de barras de las 24 horas (verde = barata, rojo = cara), la hora más barata y la más cara, y las mejores horas que quedan.
- En el **resumen diario** de Telegram.
- Por **chat**: «¿cuándo pongo la lavadora?», «¿está cara la luz ahora?».

Fuera de España, apágalo con `ARIA_LUZ=0` en `.env`.

## Gasolineras y avisos meteorológicos

- **Gasolineras**: pregunta «¿dónde echo gasolina más barata?» o «diésel barato cerca». ARIA usa los precios oficiales del Ministerio (se actualizan dos veces al día, sin claves) y te da las más baratas en un radio de 10 km (puedes pedir otro, hasta 50).
- **Avisos meteorológicos**: ARIA lee los avisos oficiales de Meteoalarm (AEMET) de tu provincia. Los amarillos salen en el resumen diario y el HUD; los **naranja y rojo** también llegan como aviso (campana, Telegram o notificación) y, si son de lluvia o viento para hoy, ARIA te propone un recordatorio para recoger la ropa o cerrar ventanas.

## Ubicación para el tiempo

Por defecto, el tiempo, los avisos y las gasolineras son los de **casa** (`ARIA_CIUDAD`). Si activas **Ajustes → Ubicación → Usar mi ubicación para el tiempo**, el navegador te pedirá permiso y, mientras ARIA esté abierta, enviará tu posición cada 15 minutos:

- Si abres ARIA en el móvil en Burgos, el resumen, el HUD, el briefing hablado y el chat te dan **el tiempo de Burgos** y los avisos de su provincia. Verás «📍 Burgos»; en casa, «🏠 Casa».
- La posición se **redondea a ~1 km** y **se borra sola a las 12 horas**. Pasado ese tiempo, vuelve a ser la de casa. **Olvidar mi ubicación** la borra al momento.
- La web nunca recibe coordenadas, solo el nombre del sitio. Los avisos automáticos de fondo siguen siendo los de casa.

## Ajustes

Los ajustes están organizados por **secciones** (a la izquierda; en el móvil, pestañas arriba) y tienen un **buscador**: escribe «telegram», «contraseña» o «voz» y verás solo las tarjetas que lo mencionan.

<p align="center"><img alt="Ajustes por secciones" src="img/captura-ajustes.png" width="100%"></p>

| Sección | Tarjetas | Quién |
|---|---|---|
| **General** | **Voz** (micrófono, leer en voz alta, manos libres, velocidad), **Ping**, **Verificación en dos pasos**, **Contraseña**, **Mis datos** y **Acerca de** | Todos (Acerca de: administradores) |
| **Ubicación** | Usar tu ubicación para el tiempo y olvidarla | Todos |
| **Avisos** | Tipos de aviso, canales, horas de silencio, resumen diario, Telegram, notificaciones y **Recordatorios** | Todos |
| **Automatización** | **Rutinas** y **Automatizaciones** («si pasa esto, haz aquello») | Todos (automatizaciones: administradores) |
| **Memoria** | Recuerdos, aprendizaje automático, diario y proyectos | Todos |
| **Inteligencia artificial** | **Cerebros** (orden, activar, Probar) y **Modelos locales** | Administradores |
| **Usuarios** | Invitar, cambiar rol, activar/desactivar, contraseña para casa, eliminar | Administradores |
| **Aplicaciones** | **Módulos**, integraciones y **Certificado** | Administradores |

### Ping

**Ping**, el hada de luz, te acompaña por ARIA. En **Ajustes → General → Ping** eliges:

- **Pasea y avisa** (por defecto): cada pocos minutos aparece, da unas vueltas por los bordes y se va volando. Si llega un aviso o una propuesta nueva, vuela hasta la campana con un bocadillo («¡Eh, mira! …») y los botones **Ver** y **Luego**; si es grave, se pone ámbar.
- **Solo avisos**: no pasea; solo aparece para avisarte.
- **Nunca**.

**Voz de Ping al avisar** reproduce su «¡Eh, mira!» (desactivada por defecto). No aparece en el Cerebro ni en el mapa, ni cuando la pestaña está oculta; con «reducir movimiento» no pasea.

### Mis datos

En **Ajustes → General → Mis datos**:

- **Descargar mis datos**: un ZIP con tus conversaciones, memoria, diario, notas, agenda, recordatorios, rutinas, finanzas, propuestas, avisos y ubicación, en JSON y con un `LEEME.txt`. No incluye contraseñas, secretos de dos pasos ni tokens.
- **Borrar mi cuenta**: escribe «BORRAR» para confirmar. Se elimina todo lo tuyo y, si eras invitado, se te quita del acceso de Cloudflare. No se puede borrar al último administrador ni hacerlo desde «Probar perfiles».

### Verificación en dos pasos

Además de la contraseña, ARIA te pedirá un código de 6 cifras de tu móvil.

1. Instala una app de autenticación (Google Authenticator, Aegis, 1Password, Microsoft Authenticator…).
2. En **Ajustes → General → Verificación en dos pasos**, pulsa **Activar** y escanea el código QR (o escribe la clave a mano).
3. Escribe el código que muestra la app y pulsa **Confirmar y activar**.
4. **Guarda los 8 códigos de recuperación** en un sitio seguro: cada uno sirve una vez si pierdes el móvil.

Al entrar, tras la contraseña, ARIA te pedirá el código. Si entras por tu dominio con Cloudflare Access, se usa el segundo factor de Access. Si un usuario pierde el móvil y los códigos, un administrador puede desactivárselo con `docker compose exec app python -m aria.dos_pasos desactivar <email>`.

## Avisos

ARIA vigila la casa en segundo plano y te avisa por la **campana**, por **Telegram** y por **notificación**:

| Aviso | Gravedad |
|---|---|
| SHIELD-DNS o HEIMDALL caídos | Grave |
| No se puede entrar desde fuera (si usas dominio) | Aviso |
| Dispositivo desconocido en la red | Aviso |
| Hallazgo grave en el escaneo de seguridad | Grave |
| Copia de seguridad fuera de casa con más de 36 h | Aviso |
| Temperatura alta, disco casi lleno o poca RAM | Grave / aviso |
| Solo responde el cerebro local durante más de 30 min | Aviso |
| Un dispositivo se conecta a la VPN (apagado por defecto) | Info |
| Empieza o termina un horario de control parental | Info |
| Avisos de tus [módulos](MODULOS.md) | Según el módulo |

Los avisos de la casa solo llegan a los administradores. En **Ajustes → Avisos** cada persona elige qué tipos quiere, por qué canales y sus **horas de silencio** (por defecto 23:00–08:00; los graves y los recordatorios llegan igual). **Probar avisos** manda uno de prueba.

## Telegram

Primero vincula tu chat (ver [instalación](INSTALACION.md#12-telegram-y-notificaciones-push)). Después puedes escribirle a ARIA como en la web: usa tus agentes, tu memoria y tus permisos. También entiende:

- **Fotos**: igual que en la web; los tickets se apuntan con los botones **Registrar** / **Cancelar**.
- **Notas de voz** (hasta 2 minutos): se transcriben. Si activas «Responder también con voz a mis notas de voz» en Ajustes → Avisos, ARIA contesta con audio.
- **Enlaces**: si mandas solo un enlace, aparece el botón **Resumir**.

Comandos:

| Comando | Qué hace |
|---|---|
| `/estado` | Resumen de la casa |
| `/resumen` | Resumen del día bien maquetado, con botones (Abrir ARIA, Agenda, Actualizar y Pausar anuncios) |
| `/tiempo` | Previsión del tiempo (`/tiempo Madrid` para otra ciudad) |
| `/recordatorios` | Tus recordatorios |
| `/rutinas` | Tus rutinas, con botones **Ejecutar ahora** y **Pausar** |
| `/gastos` | Gastos de este mes |
| `/red` | Salud de la red y dispositivos nuevos |
| `/vpn` | Dispositivos de la VPN |
| `/bloqueo` | Bloqueador de anuncios, con botones de pausa para administradores (también `/anuncios`) |
| `/copia` | Realiza una copia de seguridad cifrada al momento (administradores) |
| `/tunel` | Muestra el estado del túnel de Cloudflare y permite reiniciarlo (administradores) |
| `/nuevovpn <nombre>` | Crea un dispositivo VPN y te manda el QR y el `.conf` (administradores) |
| `/control` | Dispositivos pausados o bloqueados, con botón **Reanudar** (administradores) |
| `/lista [nombre]` | Muestra los artículos pendientes de La compra o de la lista indicada |
| `/compra <artículo>` | Añade uno o varios artículos a La compra; no repite los pendientes |
| `/informe` | Informe semanal de red y, para administradores, disponibilidad de las últimas 24 horas |
| `/nuevo` | Empieza otra conversación |
| `/desvincular` | Desvincula este chat |
| `/ayuda` | Ayuda |

<p align="center"><img alt="Resumen diario en Telegram" src="img/captura-telegram.png" width="320"></p>

Las acciones de administración piden **Confirmar**. Cada chat tiene su conversación («Telegram · …» en el historial de la web).

### Vigilante del túnel

ARIA incluye un vigilante que comprueba cada 2 minutos si la casa es accesible desde internet. Si el túnel de Cloudflare se cae, la Raspberry intenta reiniciarlo automáticamente. Puedes ver los reinicios recientes con el comando `/tunel`. En caso de caída total del túnel, siempre puedes entrar a través de la VPN **HEIMDALL**.

> El `.conf` de `/nuevovpn` contiene la clave privada del dispositivo. Bórralo del chat cuando lo hayas importado.

## Notificaciones push

Avisos en el móvil o el navegador, aunque ARIA esté cerrada. Se activan por dispositivo en **Ajustes → Avisos → Activar notificaciones en este dispositivo**. Ahí ves tus dispositivos (puedes quitarlos) y **Enviar notificación de prueba**. Necesitan entrar por una dirección con certificado válido (tu dominio). Detalles en la [instalación](INSTALACION.md#notificaciones-push).

## Atajos: Ctrl+K y Compartir

### Paleta de órdenes

**Ctrl+K** (⌘K en Mac) abre una paleta que también **busca en tus datos**: escribe dos letras o más y verás tus notas, eventos, cumpleaños, recordatorios, conversaciones y recuerdos que coinciden (sin importar tildes ni mayúsculas), agrupados por tipo. Los invitados solo buscan en lo que su acceso permite. Además sirve para: ir a cualquier sección, abrir Rutinas, Recordatorios o Avisos, empezar una conversación nueva, activar o desactivar manos libres y ejecutar una rutina. Escribe para filtrar, ↑/↓ para moverte, Intro para elegir y Esc para cerrar.

### Compartir con ARIA desde Android

1. Instala ARIA como aplicación: en Chrome, menú → **Instalar aplicación** (o **Añadir a pantalla de inicio**).
2. Desde cualquier app, pulsa **Compartir** y elige **ARIA**.
3. Se abre el chat con lo compartido y eliges **Resume esto** o **¿Qué opinas?**.

Si ya tenías ARIA instalada antes, desinstálala y vuelve a instalarla para que aparezca en el menú. Safari en iPhone no permite esta opción.

## Acceso por invitación

ARIA permite dar acceso temporal o limitado a otras personas (amigos, familiares que no viven contigo, visitas) sin que vean la configuración de tu casa ni tus datos.

### Pedir acceso

Quien entra en el **Escaparate público** (`/hola`) y pulsa **Entrar** llega a la página de **Acceso** (`/acceso`), donde verá:

1.  **Tres pasos**: una explicación de cómo funciona (pedir, esperar y entrar con email).
2.  **Formulario**: nombre, email y una frase explicando quién es o para qué quiere entrar.
3.  **Estado de su solicitud**: tras enviar el formulario, puede ver si su petición sigue **pendiente**, si ha sido **aprobada** o **rechazada** desde ese mismo navegador.
4.  **Botón «Ya tengo acceso»**: si ya le aprobaron, le lleva al login directamente.

### Gestión de invitaciones (Administradores)

Cuando alguien pide acceso, recibes un aviso por **Telegram** con botones para **Aprobar** o **Rechazar**. También puedes gestionarlo en **Ajustes → Usuarios → Accesos por invitación**.

Al aprobar, eliges un perfil. Los perfiles definen qué puede hacer el invitado:

| Ajuste | Visita | Familiar |
|---|---|---|
| **Secciones** | Inicio, Chat, Información y Mapa | Todas (incluida Finanzas y Agenda) |
| **Mensajes / día** | 20 | 200 |
| **Imágenes / día** | 0 | 20 |
| **Voz** | Local (sin gastar cuota de la casa) | Completa (la voz que tú uses) |
| **Búsqueda** | Sí | Sí |
| **Memoria** | No | Sí |
| **Telegram** | No | Sí |
| **Rutinas** | No | Sí |
| **Caducidad** | 7 días | Sin límite (o lo que tú pongas) |

Desde la gestión de invitados puedes:
- **Personalizar**: cambiar cualquier límite (secciones, mensajes, voz...) para esa persona concreta.
- **+7 días**: extender el acceso de una visita una semana más.
- **Revocar**: quitar el acceso al momento. Sus datos se conservan por si decides volver a aprobarle más adelante.

### Privacidad y seguridad

Un invitado **nunca ve**:
- La sección de **Red** ni los dispositivos de tu casa.
- La sección de **Seguridad** ni el **Centro de control**.
- Los anuncios bloqueados ni el estado de la **VPN**.
- La temperatura o carga de la **Raspberry**.
- Los datos de administración ni de otros usuarios.

El acceso **caduca solo**: cuando llega la fecha, el usuario deja de tener acceso a ARIA y se le quita automáticamente de Cloudflare Access.

### Probar perfiles

Para ver exactamente qué verá un invitado antes de aprobarlo, usa el modo **Probar perfiles** en **Ajustes → Usuarios → Accesos por invitación**:

- Pulsa **Ver ARIA como...** y elige **Usuario**, **Familiar** o **Visita**.
- ARIA se recargará y verás una **barra ámbar** arriba avisando de que estás en una vista de prueba.
- Navega por las secciones para comprobar qué está oculto o limitado.
- Pulsa **Salir de la vista** en la barra ámbar para volver a tu usuario administrador.

## Usuarios y roles

ARIA admite varias personas, cada una con sus conversaciones, memoria, finanzas, recordatorios y rutinas.

| | Administrador | Usuario |
|---|---|---|
| Inicio | Completo, con acciones rápidas y «Copiar contraseña» | Solo estado |
| Chat | Todas las herramientas | Solo consultas (no pausa el bloqueador ni toca la VPN) |
| Agentes | Todos | ARIA, Finanzas y Redes (solo consulta) |
| Finanzas | Las suyas | Las suyas |
| Red, Seguridad, Control | Sí | No |
| Ajustes | Todo | Avisos, recordatorios, rutinas, voz, memoria y contraseña |

Los permisos se comprueban **en el servidor**, no solo ocultando botones.

**Invitar a alguien**: **Ajustes → Usuarios → Invitar usuario** (email, nombre y rol). Para que entre desde casa, pulsa **Poner contraseña para casa**. Si usas Cloudflare Access, añade también su email a la política de ARIA en Cloudflare para que pueda entrar desde fuera. Desde Usuarios puedes cambiar el rol, desactivar (sus sesiones se cierran al momento) o eliminar a alguien. Nunca se puede quitar al último administrador activo.


### Registro de actividad

Solo para administradores, en **Ajustes → Usuarios → Registro de actividad**: qué herramienta usó cada agente, para quién, desde dónde (chat, Telegram, rutina, automatización o propuesta), con qué resultado y cuánto tardó.

- Filtros por usuario, por herramienta y **Solo errores**.
- Las contraseñas, claves y códigos que aparezcan en los datos se guardan como «***».
- Se guarda 30 días.

## Cuando algo falla

ARIA está pensada para seguir funcionando aunque algo se caiga:

```mermaid
flowchart LR
    O["Ollama Cloud"] -- "falla" --> G["Groq"]
    G -- "falla" --> M["Gemini"]
    M -- "falla" --> L["Local"]
```

- **Cerebros**: si el primero falla (límite gratuito, clave, sin conexión o más de 30 s), pasa al siguiente: Ollama Cloud → Groq → Gemini → local. El que falló por límite se salta un rato (unos 15 minutos o lo que diga el proveedor). Si al final solo queda el local, las respuestas serán más lentas, y si dura más de 30 minutos recibirás un aviso. Puedes ver y probar cada uno en Ajustes → Cerebros.
- **Voz de ARIA**: Gemini («Leda») → voz local en tu máquina (Piper) → voz del navegador.
- **Transcripción**: Groq → Whisper en tu máquina (más lento y menos preciso).
- **Visión**: Gemini → Groq. Sin ninguno, ARIA te dice que ahora no puede ver imágenes.
- **Rutinas**: sin cerebros de la nube, se saltan y te dejan una nota.
- **SHIELD-DNS caído**: lo que pidas en control parental queda guardado y se aplica en cuanto vuelva.
- **Un módulo roto**: queda en «Error» en Ajustes → Módulos y ARIA sigue funcionando.
- **Contenedores colgados**: si instalaste la [autocuración](INSTALACION.md#14-autocuración), se reinician solos.

Si algo sigue sin ir, mira los [problemas frecuentes](INSTALACION.md#17-problemas-frecuentes).
