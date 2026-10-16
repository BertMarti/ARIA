# ARIA para Android

Aplicación Capacitor 7 que pregunta la URL segura de una instalación ARIA, la abre en su WebView y añade atajos, widget, tile, avisos y actualización desde GitHub. La dirección y las cookies no salen de la aplicación.

## Compilar y publicar

Desde `movil/aria`: `npm install`, `npx cap sync android` y `cd android && ./gradlew assembleRelease`. `ARIA_VERSION` y `ARIA_VERSION_CODE` están en `android/gradle.properties`. La publicación se realiza con `herramientas/app/publicar.sh` desde la raíz del proyecto.

Permisos: Internet para conectar con ARIA y GitHub; notificaciones para los avisos; instalación de paquetes para ofrecer actualizaciones descargadas desde GitHub. No se solicita ubicación, contactos, cámara ni micrófono.
