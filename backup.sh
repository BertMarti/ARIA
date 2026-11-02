#!/usr/bin/env bash
# Copia de seguridad de ARIA: .env + data/ (conversaciones, ajustes, token de Spotify).
# No incluye los modelos de Ollama (se pueden volver a descargar). Uso: ./backup.sh
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
error() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

[ -f .env ] || error "No existe .env: no hay nada que copiar."
mkdir -p backups
chmod 700 backups
destino="backups/aria-$(date +%Y%m%d-%H%M).tar.gz"

# ARIA sigue en marcha mientras se copia: la base de datos se copia con la API de copia de SQLite (una foto
# coherente, aunque se esté escribiendo) y el resto de data/ va sin lo que se regenera solo ni las copias locales
# que se hacen al desplegar (aria.db.bak-*).
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
foto=()
if [ -f data/aria.db ]; then
  python3 - data/aria.db "$tmp/aria.db" <<'PY'
import sqlite3, sys
origen = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=30)
destino = sqlite3.connect(sys.argv[2])
origen.backup(destino)
destino.close(); origen.close()
PY
  foto=(--transform 's|^aria\.db$|data/aria.db|' -C "$tmp" aria.db -C "$PWD")
fi
excluir=(--exclude='data/aria.db' --exclude='data/aria.db-*' --exclude='data/aria.db.bak*'
         --exclude='data/grabaciones' --exclude='data/backups')
archivos=(.env)
[ -d data ] && archivos+=(data)

empaquetar() {   # tar sale con 1 si un archivo cambió mientras se leía (registros, cachés): no es un fallo
  local r=0
  "$@" -czf "$destino" --warning=no-file-changed "${excluir[@]}" "${foto[@]}" "${archivos[@]}" 2>"$tmp/errores" || r=$?
  [ "$r" -le 1 ]
}
info "Creando $destino"
if ! empaquetar tar; then
  # Algún archivo de data/ puede pertenecer a otro usuario (p. ej. root): se reintenta con sudo.
  info "Permisos insuficientes: reintentando con sudo"
  empaquetar sudo tar || { cat "$tmp/errores" >&2; error "No se pudo crear la copia"; }
  sudo chown "$(id -u):$(id -g)" "$destino"
fi
chmod 600 "$destino"

# Conserva solo las 7 copias más recientes.
ls -1t backups/aria-*.tar.gz 2>/dev/null | tail -n +8 | while read -r viejo; do
  info "Borrando copia antigua: $viejo"
  rm -f -- "$viejo"
done

info "Listo: $destino ($(du -h "$destino" | cut -f1))"
echo "  Contiene secretos (.env): guárdala fuera de la Pi y no la subas a git."
