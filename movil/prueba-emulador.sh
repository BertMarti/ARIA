#!/bin/sh
# Prueba de humo de las apps en un Android emulado (la llama .github/workflows/android.yml).
# Instala, abre por todos los caminos de entrada, guarda capturas y falla si alguna app se cierra.
set -u
mkdir -p capturas
adb install -r apk/aria-prueba.apk
adb install -r apk/aria-lite-prueba.apk || true
adb logcat -c
adb shell am start -n io.github.bertmarti.aria/.MainActivity
sleep 15
adb exec-out screencap -p > capturas/aria-inicio.png
# Como un móvil ya configurado: se escribe una dirección (no hace falta que sea ARIA) y se repiten las entradas
# del widget («Hablar» y «Nota») con la app abierta y con la app cerrada, que es como las usa la gente.
adb shell input tap 540 1200 || true
sleep 1
adb shell input text "https://example.com" || true
adb shell input keyevent 66 || true
sleep 8
adb exec-out screencap -p > capturas/aria-configurada.png
for accion in hablar nota avisos; do
  adb shell am start -n io.github.bertmarti.aria/.MainActivity -f 0x30000000 --es accion "$accion"   # abierta
  sleep 4
  adb exec-out screencap -p > "capturas/widget-$accion-abierta.png"
  adb shell am force-stop io.github.bertmarti.aria
  adb shell am start -n io.github.bertmarti.aria/.MainActivity -f 0x30000000 --es accion "$accion"   # cerrada
  sleep 6
  adb exec-out screencap -p > "capturas/widget-$accion-cerrada.png"
done
for accion in hablar nota hud compartir cambiar; do
  adb shell am start -n io.github.bertmarti.aria/.MainActivity --es accion "$accion"
  sleep 3
done
adb shell am start -a android.intent.action.SEND -t text/plain --es android.intent.extra.TEXT "Prueba" \
  -n io.github.bertmarti.aria/.MainActivity
sleep 3
adb shell am start -a android.intent.action.ASSIST -p io.github.bertmarti.aria || true
sleep 4
adb exec-out screencap -p > capturas/aria-asistente.png
adb shell monkey -p io.github.bertmarti.aria.lite -c android.intent.category.LAUNCHER 1
sleep 8
adb exec-out screencap -p > capturas/aria-lite-config.png
adb shell cmd statusbar expand-settings || true
sleep 3
adb exec-out screencap -p > capturas/ajustes-rapidos.png
adb logcat -d > capturas/logcat.txt
if grep -E "FATAL EXCEPTION|AndroidRuntime: Process: io.github.bertmarti" capturas/logcat.txt; then
  echo "Una app se ha cerrado"
  exit 1
fi
echo "Sin cierres"
