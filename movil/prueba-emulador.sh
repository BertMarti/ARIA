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
# El campo se busca en la jerarquía de la pantalla (las coordenadas fijas fallan si cambia la resolución del emulador).
adb shell uiautomator dump /sdcard/pantalla.xml >/dev/null 2>&1 || true
CAMPO=$(adb shell cat /sdcard/pantalla.xml 2>/dev/null | tr '>' '\n' | grep 'class="android.widget.EditText"' \
  | sed -n 's/.*bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]".*/\1 \2 \3 \4/p' | head -1)
if [ -n "$CAMPO" ]; then
  set -- $CAMPO
  adb shell input tap $(( ($1 + $3) / 2 )) $(( ($2 + $4) / 2 ))
else
  # La página de la WebView no siempre sale en la jerarquía: el campo ya tiene el foco (autofocus).
  echo "El campo no sale en la jerarquía; uso el foco automático"
fi
sleep 1
adb shell input text "https://example.com" || true
adb shell input keyevent 66 || true
sleep 8
adb exec-out screencap -p > capturas/aria-configurada.png
adb shell cat /data/data/io.github.bertmarti.aria/shared_prefs/CapacitorStorage.xml 2>/dev/null | grep -q aria_url \
  && echo "Dirección guardada" || echo "Aviso: la dirección no se ha guardado (la prueba del widget no cubre una app configurada)"
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
