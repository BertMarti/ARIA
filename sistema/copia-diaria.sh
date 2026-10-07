#!/usr/bin/env bash
# Copia de seguridad diaria del homelab, cifrada y guardada FUERA de la Raspberry.
#  1. Ejecuta backup.sh de ARIA, HEIMDALL y SHIELD-DNS.
#  2. Junta la copia más reciente de cada uno + ~/homelab/cloudflare.env en un único archivo.
#  3. Lo cifra con AES-256 (gpg, contraseña en ~/homelab/.clave-copias).
#  4. Lo sube al repositorio privado de GitHub indicado en COPIAS_REPO y conserva las 14 últimas.
# Uso: ./sistema/copia-diaria.sh   (lo lanza cada día el timer homelab-copias)
# Restaurar: ver README → "Copias de seguridad fuera de la Pi".
set -euo pipefail

HOMELAB_DIR="${HOMELAB_DIR:-$HOME/homelab}"
CLAVE="${COPIAS_CLAVE:-$HOMELAB_DIR/.clave-copias}"
REPO="${COPIAS_REPO:-$(gh api user -q .login)/homelab-copias}"
LOCAL="$HOMELAB_DIR/.copias-repo"
CONSERVAR="${COPIAS_CONSERVAR:-14}"
FECHA="$(date +%Y%m%d-%H%M)"

log() { echo "$*"; logger -t homelab-copias "$*" 2>/dev/null || true; }
[ -s "$CLAVE" ] || { log "Falta la contraseña de cifrado en $CLAVE (ejecuta sistema/instalar-copias.sh)"; exit 1; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/homelab"

for p in SHIELD-DNS HEIMDALL ARIA; do
  d="$HOMELAB_DIR/$p"
  [ -x "$d/backup.sh" ] || { log "Se omite $p (no instalado)"; continue; }
  (cd "$d" && ./backup.sh >/dev/null) || { log "ERROR: falló la copia de $p"; exit 1; }
  ultimo="$(ls -1t "$d"/backups/*.tar.gz 2>/dev/null | head -1)"
  [ -n "$ultimo" ] && cp "$ultimo" "$TMP/homelab/" && log "Incluida $(basename "$ultimo")"
done
[ -f "$HOMELAB_DIR/cloudflare.env" ] && cp "$HOMELAB_DIR/cloudflare.env" "$TMP/homelab/"

ARCH="homelab-$FECHA.tar.gz.gpg"
tar -czf - -C "$TMP" homelab | gpg --batch --yes --quiet --pinentry-mode loopback \
  --passphrase-file "$CLAVE" --symmetric --cipher-algo AES256 -o "$TMP/$ARCH"

if [ ! -d "$LOCAL/.git" ]; then
  gh repo clone "$REPO" "$LOCAL" -- -q
fi
cd "$LOCAL"
git pull -q --ff-only 2>/dev/null || true
cp "$TMP/$ARCH" .
ls -1t homelab-*.tar.gz.gpg | tail -n +"$((CONSERVAR + 1))" | xargs -r git rm -q --
git add "$ARCH"
git commit -qm "Copia $FECHA" && git push -q origin HEAD
log "Copia cifrada subida: $REPO/$ARCH ($(du -h "$ARCH" | cut -f1))"
# Estado para el resumen de buenos días de ARIA (solo fecha y nombre, nada sensible)
if [ -d "$HOMELAB_DIR/ARIA/data" ]; then
  printf '{"fecha": "%s", "archivo": "%s"}\n' "$(date -Iseconds)" "$ARCH" > "$HOMELAB_DIR/ARIA/data/ultima-copia.json"
fi
