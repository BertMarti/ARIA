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
archivos=(.env)
[ -d data ] && archivos+=(data)

info "Creando $destino"
if ! tar -czf "$destino" "${archivos[@]}" 2>/dev/null; then
  # Algún archivo de data/ puede pertenecer a otro usuario (p. ej. root): se reintenta con sudo.
  info "Permisos insuficientes: reintentando con sudo"
  sudo tar -czf "$destino" "${archivos[@]}"
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
