#!/bin/sh
# Publica las apps de Android de ARIA 3 (ARIA y ARIA Lite) en GitHub Releases.
# GitHub Actions las compila SIN FIRMAR; aquí se firman con la llave que vive solo en esta máquina
# (ARIA_CLAVES_APP, por defecto ~/homelab/.claves-app: aria.jks + clave.txt + herramientas/apksigner.jar).
#
# Uso: herramientas/app/publicar.sh [--probar] [ID_DE_EJECUCIÓN]
#   --probar  firma y verifica pero NO publica (deja las APK en /tmp)
#   sin ID    usa la última compilación correcta del flujo «Android» de la rama actual
set -eu
REPO="${ARIA_REPO_GH:-BertMarti/ARIA}"
CLAVES="${ARIA_CLAVES_APP:-$HOME/homelab/.claves-app}"
PROBAR=0
[ "${1:-}" = "--probar" ] && { PROBAR=1; shift; }
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
VERSION=$(sed -n 's/^ARIA_VERSION=//p' "$RAIZ/movil/aria/android/gradle.properties" 2>/dev/null || true)
[ -n "$VERSION" ] || VERSION=$(sed -n 's/^ARIA_VERSION=//p' "$RAIZ/movil/aria/gradle.properties" 2>/dev/null || true)
[ -n "$VERSION" ] || { echo "No encuentro ARIA_VERSION en gradle.properties"; exit 1; }
RAMA=$(git -C "$RAIZ" rev-parse --abbrev-ref HEAD)
RUN="${1:-$(gh run list --repo "$REPO" --workflow Android --branch "$RAMA" --status success --limit 1 --json databaseId --jq '.[0].databaseId')}"
[ -n "$RUN" ] && [ "$RUN" != "null" ] || { echo "No hay ninguna compilación correcta de Android en $RAMA"; exit 1; }
for f in aria.jks clave.txt herramientas/apksigner.jar; do [ -r "$CLAVES/$f" ] || { echo "Falta $CLAVES/$f"; exit 1; }; done

TRABAJO=$(mktemp -d)
trap 'rm -rf "$TRABAJO/sin-firmar"' EXIT
gh run download "$RUN" --repo "$REPO" --name apk-sin-firmar --dir "$TRABAJO/sin-firmar"
for app in aria aria-lite; do
  entrada="$TRABAJO/sin-firmar/$app-sin-firmar.apk"
  [ -f "$entrada" ] || { echo "(sin $app en esta compilación)"; continue; }
  salida="$TRABAJO/$app-$VERSION.apk"
  # La contraseña se lee de un archivo: no aparece en la línea de órdenes ni en el historial.
  java -jar "$CLAVES/herramientas/apksigner.jar" sign --ks "$CLAVES/aria.jks" --ks-key-alias aria \
    --ks-pass "file:$CLAVES/clave.txt" --out "$salida" "$entrada"
  java -jar "$CLAVES/herramientas/apksigner.jar" verify --print-certs "$salida" | grep -i "SHA-256 digest" | head -1
  echo "Firmada: $salida"
done
if [ "$PROBAR" = 1 ]; then echo "Modo prueba: no se publica. APK en $TRABAJO"; exit 0; fi
NOTAS="ARIA $VERSION para Android. «aria-$VERSION.apk» es la app completa (widgets, avisos, atajos y actualizaciones);
«aria-lite-$VERSION.apk» es la versión ligera (la web de ARIA a pantalla completa). Al abrirla, escribe la dirección de tu ARIA
(Ajustes → App de Android). Compilada por GitHub Actions (ejecución $RUN) y firmada fuera de GitHub."
gh release create "app-v$VERSION" --repo "$REPO" --title "ARIA $VERSION para Android" --notes "$NOTAS" \
  --target "$(git -C "$RAIZ" rev-parse HEAD)" "$TRABAJO"/*.apk
echo "Publicada app-v$VERSION"
