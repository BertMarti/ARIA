<p align="center">
  <sub>Parte del ecosistema ARIA&nbsp;&nbsp;·&nbsp;&nbsp;<a href="https://github.com/BertMarti/ARIA">🤖 ARIA</a></sub>
  <br>
  <a href="../README.md">🏠 README</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="INSTALACION.md">📘 Instalación</a>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="USO.md">🧭 Uso</a>&nbsp;&nbsp;·&nbsp;&nbsp;<b>📱 App de Android</b>&nbsp;&nbsp;·&nbsp;&nbsp;<a href="PLAN.md">🗺️ Hoja de ruta</a>
</p>

# App de Android

ARIA 3 tiene dos aplicaciones para Android. Las dos necesitan una instalación de ARIA accesible por HTTPS.

## ARIA o ARIA Lite

| | ARIA | ARIA Lite |
|---|---|---|
| Base | Capacitor 7 y WebView | Trusted Web Activity (TWA) |
| Qué ofrece | La web de ARIA y funciones de Android: móvil vinculado, widget, mosaico de ajustes rápidos, atajos, compartir, avisos en segundo plano y actualizaciones | La web de ARIA a pantalla completa |
| Avisos | Comprueba el resumen cada 15 minutos cuando hay red y muestra los avisos nuevos | No añade avisos en segundo plano |
| Widget | Tiempo, próximo evento, avisos sin leer y botones Hablar y Nota | No incluye widget ni resumen en segundo plano |
| Asistente y palabra «Aria» | Puede ser la app de asistencia digital y ofrece la escucha experimental sin conexión | No incluye estas funciones nativas |
| Actualizaciones | Las busca en GitHub y permite instalarlas desde la propia app | Se actualiza instalando una nueva APK desde GitHub Releases |
| Si falla el vínculo con la web | Sigue usando su WebView | Chrome abre una Custom Tab con barra de dirección |

Elige **ARIA** si quieres la integración completa con Android. Elige **ARIA Lite** si solo quieres abrir tu ARIA como una aplicación ligera.

## Instalarla

1. Abre [GitHub Releases](https://github.com/BertMarti/ARIA/releases) desde el móvil.
2. Descarga `aria-<versión>.apk` o `aria-lite-<versión>.apk`.
3. Si Android lo pide, permite una vez que el navegador o el gestor de archivos instale aplicaciones desde esa fuente.
4. Abre la APK y confirma la instalación.

También puedes añadir el repositorio a [Obtainium](https://github.com/ImranR98/Obtainium). Obtainium comprueba las Releases y descarga las actualizaciones por ti.

## Primera vez

1. Abre la aplicación.
2. Escribe la dirección de tu ARIA, por ejemplo `https://aria.ejemplo.es`.
3. Inicia sesión como siempre, con tu contraseña o con Cloudflare Access si lo tienes configurado.

ARIA guarda la dirección solo en el móvil. Desde sus ajustes puedes cambiarla para conectar con otra instalación.

## Móvil vinculado

Al iniciar sesión, ARIA vincula el móvil en segundo plano. La aplicación crea un token de dispositivo para leer un resumen limitado, aunque caduque la sesión web. Ese resumen contiene únicamente los avisos sin leer, el tiempo y tu próximo evento, y permite que funcionen los avisos y el widget.

El token se guarda en el móvil y caduca a los 180 días. En el servidor nunca se guarda el token, sino solo su huella. Puedes revocar un móvil desde **Ajustes → General → App de Android → Móviles vinculados**. Al cambiar de instalación, la aplicación borra el vínculo local.

Si vas a usarlo desde fuera de casa, Cloudflare Access debe dejar pasar **solo** la ruta `/api/app/resumen` para este uso. Esa ruta solo acepta el token de dispositivo y no sustituye al inicio de sesión para el resto de ARIA. No abras el resto de la aplicación sin autenticación.

## Siri en iPhone y iPad

1. En ARIA, abre **Ajustes → General → App de Android → Atajos de iPhone y iPad (Siri)**.
2. Pulsa **Crear token para Atajos** y conserva el token que aparece. Solo se muestra una vez; si lo pierdes, crea otro y revoca el anterior.
3. Abre la app **Atajos**, pulsa **Nuevo atajo** y añade la acción **Obtener contenido de URL**.
4. Usa `https://aria.ejemplo.es/api/app/resumen?formato=texto` con método **GET**.
5. En **Cabeceras**, añade `Authorization` con el valor `Bearer <token>` usando el token creado en ARIA.
6. Añade **Leer texto** o **Mostrar resultado**.
7. Llama al atajo **Resumen de ARIA** y dile a Siri: «Resumen de ARIA».

El token solo permite leer el resumen personal y caduca como los demás tokens de dispositivo. Si lo usas desde fuera de casa, Cloudflare Access debe dejar pasar `/api/app/resumen`.

## Qué añade ARIA

La aplicación completa añade:

- **Cuatro widgets** de pantalla de inicio: **Resumen**; **Hablar** (1×1); **Agenda**, con los tres próximos eventos; y **Casa**, con anuncios bloqueados, VPN y estado de los servicios. El widget Casa es solo para administradores.
- **Mosaico de ajustes rápidos** para abrir ARIA rápidamente.
- **Plan B ante bloqueos** (por ejemplo, los de LaLiga a IP de Cloudflare): si la dirección pública no responde, la app y los widgets entran solos por la dirección de casa (en tu wifi o con la VPN HEIMDALL), fiándose solo de certificados firmados por la autoridad de tu casa. Si no hay forma, la app lo explica y ofrece conectar la VPN. Hace falta haber abierto la app al menos una vez con la dirección normal funcionando.
- **Informe de cierres**: si la app se cierra, guarda la causa (sin tus datos ni la dirección de ARIA) y la manda a tu ARIA la próxima vez que la abres. Los administradores reciben un aviso y lo ven en **Ajustes → App de Android → Cierres recientes**.
- **Atajos** para hablar, activar manos libres, crear una nota, abrir el HUD, compartir, cambiar de instalación y buscar actualizaciones.
- **Compartir**: elige ARIA en el menú Compartir de otra aplicación para enviarle texto o un enlace.
- **Avisos en segundo plano**: consulta el resumen del móvil vinculado cada 15 minutos como mínimo, cuando Android y la red lo permiten, y muestra los avisos nuevos.
- **Actualizaciones desde la propia app**: comprueba GitHub Releases y descarga la nueva APK. Android confirma la instalación.

Los atajos web de `#hablar`, `#manos-libres`, `#nota`, `#hud` y `#compartir` abren la acción correspondiente de ARIA.

Para añadirlos al escritorio, mantén pulsado un espacio vacío, toca **Widgets** y busca **ARIA**. El icono nuevo de la app sigue el de la web con una versión temática.

## Permisos

| Permiso | Para qué sirve |
|---|---|
| Internet | Conectar con tu ARIA y consultar GitHub Releases. |
| Notificaciones | Mostrar avisos de ARIA. Solo lo solicita la app completa. |
| Instalar paquetes | Permitir que la app completa ofrezca una APK descargada desde GitHub. Android pide confirmación y puedes revocarlo. |
| Micrófono | Escuchar la palabra «Aria» cuando activas esta función experimental. Solo lo solicita la app completa y la escucha se hace en el móvil. |
| Servicio en primer plano de micrófono | Mantener visible la notificación fija mientras la escucha experimental está activa. Solo lo solicita la app completa. |

No se solicitan ubicación, contactos ni cámara. El micrófono de la conversación web sigue siendo un permiso de la web y del navegador WebView; el permiso nativo de micrófono solo se pide al activar «Escuchar “Aria”».

## Hablar con ARIA sin tocar la pantalla

### Como asistente digital

1. Ve a **Ajustes de Android → Aplicaciones → Aplicaciones predeterminadas → App de asistencia digital**.
2. Elige **ARIA**.
3. Abre ARIA manteniendo pulsado el botón de inicio o el de encendido, según el modelo y la versión de Android.

La aplicación también ofrece el atajo **Usar ARIA como asistente**, que abre directamente estos ajustes cuando Android lo permite.

### Escuchar «Aria» (experimental)

Actívalo desde el mosaico de ajustes rápidos o desde el atajo **Escuchar “Aria”**. La primera vez descarga una vez un modelo de voz en español de unos 39 MB. Después escucha sin conexión en el propio móvil: no sale ningún audio del dispositivo ni se guarda.

Mientras está activo aparece una notificación fija con una acción para pararlo. La escucha se detiene con la batería por debajo del 15 % o al activar el ahorro de batería, y no se reactiva automáticamente después de reiniciar el teléfono. Consume batería, por lo que es una función experimental.

## Privacidad y seguridad

- La app no lleva ningún dominio fijado. Tú escribes la dirección de tu ARIA.
- La dirección y las cookies se quedan en el móvil. No se envían a la aplicación ni a un servicio intermedio.
- Las actualizaciones solo se buscan en GitHub Releases.
- Android exige que una actualización tenga la misma firma que la aplicación instalada. Por eso una APK firmada con otra llave no puede actualizarla.
- La TWA de ARIA Lite se vincula al dominio mediante `/.well-known/assetlinks.json`. Si no se puede comprobar, Chrome usa una Custom Tab con barra de dirección.

## Cómo se construye y publica

GitHub Actions compila las dos APK sin firmar y prueba cada compilación en un Android 13 emulado. El flujo `Android` usa Java 21 y Node 22, guarda el artefacto `apk-sin-firmar` durante 14 días y nunca recibe la llave de firma.

La llave vive solo en la máquina de ARIA. `herramientas/app/publicar.sh` descarga la compilación, firma `aria` y `aria-lite`, verifica el certificado y publica las APK en una GitHub Release. La contraseña de la llave se lee desde un archivo, no desde la línea de órdenes.

Para que la TWA no muestre la barra de dirección, añade en `.env` la huella SHA-256 del certificado de firma:

```bash
ARIA_APP_SHA256=AA:BB:CC:DD:...:11
```

ARIA sirve esa huella en `/.well-known/assetlinks.json` para los paquetes de ARIA y ARIA Lite. Si hay más de una firma válida, sepáralas por comas. Cloudflare Access debe dejar pasar `/.well-known/assetlinks.json` sin pedir inicio de sesión. La ruta es pública y no contiene datos de tu instalación.

## Problemas frecuentes

| Problema | Solución |
|---|---|
| La TWA muestra la barra de dirección | Comprueba que `ARIA_APP_SHA256` contiene la huella de la APK publicada, que `assetlinks.json` responde sin sesión y que Cloudflare Access no bloquea esa ruta. Desinstala y vuelve a instalar si Android conservó el vínculo anterior. |
| No llegan los avisos | Abre ARIA para renovar la sesión, comprueba las notificaciones y permite el uso de red en segundo plano. Android puede retrasar las tareas de 15 minutos para ahorrar batería. |
| El widget pide vincular | Abre ARIA e inicia sesión. El móvil se vincula en segundo plano y el widget recibe el resumen cuando haya red. |
| No funciona desde fuera de casa | Comprueba que Cloudflare Access deja pasar únicamente `/api/app/resumen` para el token de dispositivo y que el móvil vinculado no ha caducado ni se ha revocado. |
| No se activa «Aria» | Concede el permiso de micrófono y desactiva el ahorro de batería. La escucha no funciona con batería inferior al 15 % y necesita descargar el modelo la primera vez. |
| Sale «app no instalada» al actualizar | La APK tiene una firma distinta. Desinstala la app anterior e instala la nueva, o publica siempre con la misma llave. |
| Android no deja instalar la APK | Activa una vez «Permitir instalar aplicaciones desde esta fuente» para el navegador o gestor de archivos que la descargó. |
| No se abre tu ARIA | Comprueba que la dirección empieza por `https://` y que responde desde el móvil. La primera conexión debe completar el inicio de sesión normalmente. |

## Qué viene después

La hoja de ruta de ARIA 3.x se mantiene en [PLAN.md](PLAN.md). La app ya incluye el asistente predeterminado, la palabra «Aria» experimental, el resumen para avisos y el widget; el envío a la tele se cubre por ahora con **Compartir** dentro de la app.
