# ARIA Lite

Aplicación Android mínima basada en Trusted Web Activity. La primera vez pide la
dirección HTTPS de tu ARIA y la guarda únicamente en el dispositivo. Chrome
comprueba `/.well-known/assetlinks.json`; si no puede verificar el vínculo, abre
la web con la barra de dirección mediante Custom Tab.

El proyecto se compila con `./gradlew assembleRelease`. La versión se controla
con `ARIA_VERSION` y `ARIA_VERSION_CODE` en `gradle.properties`.
