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
| Qué ofrece | La web de ARIA y funciones de Android: widget, mosaico de ajustes rápidos, atajos, compartir, avisos en segundo plano y actualizaciones | La web de ARIA a pantalla completa |
| Avisos | Comprueba los avisos cada 15 minutos cuando hay red | No añade avisos en segundo plano |
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

## Qué añade ARIA

La aplicación completa añade:

- **Widget** de pantalla de inicio con accesos para hablar y crear una nota.
- **Mosaico de ajustes rápidos** para abrir ARIA rápidamente.
- **Atajos** para hablar, activar manos libres, crear una nota, abrir el HUD, compartir, cambiar de instalación y buscar actualizaciones.
- **Compartir**: elige ARIA en el menú Compartir de otra aplicación para enviarle texto o un enlace.
- **Avisos en segundo plano**: comprueba la instalación cada 15 minutos como mínimo, cuando Android y la red lo permiten.
- **Actualizaciones desde la propia app**: comprueba GitHub Releases y descarga la nueva APK. Android confirma la instalación.

Los atajos web de `#hablar`, `#manos-libres`, `#nota`, `#hud` y `#compartir` abren la acción correspondiente de ARIA.

## Permisos

| Permiso | Para qué sirve |
|---|---|
| Internet | Conectar con tu ARIA y consultar GitHub Releases. |
| Notificaciones | Mostrar avisos de ARIA. Solo lo solicita la app completa. |
| Instalar paquetes | Permitir que la app completa ofrezca una APK descargada desde GitHub. Android pide confirmación y puedes revocarlo. |

No se solicitan ubicación, contactos, cámara ni micrófono. El micrófono y la cámara, si los usas, siguen siendo permisos de la web y del navegador WebView.

## Privacidad y seguridad

- La app no lleva ningún dominio fijado. Tú escribes la dirección de tu ARIA.
- La dirección y las cookies se quedan en el móvil. No se envían a la aplicación ni a un servicio intermedio.
- Las actualizaciones solo se buscan en GitHub Releases.
- Android exige que una actualización tenga la misma firma que la aplicación instalada. Por eso una APK firmada con otra llave no puede actualizarla.
- La TWA de ARIA Lite se vincula al dominio mediante `/.well-known/assetlinks.json`. Si no se puede comprobar, Chrome usa una Custom Tab con barra de dirección.

## Cómo se construye y publica

GitHub Actions compila las dos APK sin firmar. El flujo `Android` usa Java 21 y Node 22, guarda el artefacto `apk-sin-firmar` durante 14 días y nunca recibe la llave de firma.

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
| Sale «app no instalada» al actualizar | La APK tiene una firma distinta. Desinstala la app anterior e instala la nueva, o publica siempre con la misma llave. |
| Android no deja instalar la APK | Activa una vez «Permitir instalar aplicaciones desde esta fuente» para el navegador o gestor de archivos que la descargó. |
| No se abre tu ARIA | Comprueba que la dirección empieza por `https://` y que responde desde el móvil. La primera conexión debe completar el inicio de sesión normalmente. |

## Qué viene después

La hoja de ruta de ARIA 3.x contempla:

- **Palabra de activación nativa**, sin tener que abrir la app.
- **Enviar a la tele nativo**.
- **Notificaciones push sin abrir la app**.
