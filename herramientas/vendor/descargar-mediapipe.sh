#!/bin/sh
# Descarga los archivos grandes de MediaPipe (gestos del HUD) que no se guardan en git, con versión fija y huella comprobada.
# Uso: herramientas/vendor/descargar-mediapipe.sh   (idempotente; lo llama install.sh)
set -eu
cd "$(dirname "$0")/../.."
DEST=app/static/vendor/mediapipe
mkdir -p "$DEST/wasm"
baja() {   # baja URL DESTINO SHA256
  if [ -f "$2" ] && echo "$3  $2" | sha256sum -c - >/dev/null 2>&1; then return 0; fi
  tmp="$2.tmp"; curl -fsSL "$1" -o "$tmp"
  if [ -n "${4:-}" ]; then   # dentro de un paquete npm (.tgz)
    d=$(mktemp -d); tar xzf "$tmp" -C "$d" "package/$4"; mv "$d/package/$4" "$tmp"; rm -rf "$d"
  fi
  echo "$3  $tmp" | sha256sum -c - >/dev/null || { rm -f "$tmp"; echo "✘ Huella incorrecta: $1" >&2; exit 1; }
  mv "$tmp" "$2"; chmod 644 "$2"
}
baja https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-1.0.1.tgz "$DEST/wasm/vision_wasm_internal.wasm" 8da277a733926eacd0474b8704b36742d6ec3231c57a860c5b889dff8f1df886 wasm/vision_wasm_internal.wasm
baja https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task "$DEST/hand_landmarker.task" fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1
echo "✔ MediaPipe listo en $DEST"
