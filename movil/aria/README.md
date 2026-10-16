# ARIA para Android

Aplicación Capacitor 7 que pregunta la URL segura de una instalación ARIA, la abre en su WebView y añade atajos, widget, tile, avisos y actualización desde GitHub. La dirección y las cookies no salen de la aplicación.

## Compilar y publicar

Desde `movil/aria`: `npm install`, `npx cap sync android` y `cd android && ./gradlew assembleRelease`. `ARIA_VERSION` y `ARIA_VERSION_CODE` están en `android/gradle.properties`. La publicación se realiza con `herramientas/app/publicar.sh` desde la raíz del proyecto.

Permisos: Internet para conectar con ARIA y GitHub; notificaciones para los avisos; instalación de paquetes para ofrecer actualizaciones descargadas desde GitHub. No se solicita ubicación, contactos ni cámara.

## Hablar sin tocar la pantalla

Para usar ARIA como asistente, abre Ajustes de Android → Aplicaciones → Aplicaciones predeterminadas → App de asistencia digital → ARIA. La aplicación también ofrece el atajo «Usar ARIA como asistente» para abrir esa pantalla.

La escucha de la palabra «Aria» es experimental y está desactivada por defecto. Actívala desde el atajo «Escuchar “Aria”» o desde su mosaico de ajustes rápidos; solicita micrófono, descarga una vez el modelo local de Vosk y no guarda ni envía audio. Se detiene automáticamente con batería inferior al 15 % o en modo ahorro de batería, y no se reactiva después de reiniciar el teléfono.
