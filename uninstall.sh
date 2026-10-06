#!/usr/bin/env bash
# Desinstala ARIA: para y elimina los contenedores. Con --purge borra tambien datos y volumenes.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

PURGE=0
case "${1:-}" in
  "") ;;
  --purge) PURGE=1 ;;
  *) echo "Uso: ./uninstall.sh [--purge]" >&2; exit 1 ;;
esac

if [ "$PURGE" = 1 ]; then
  read -r -p "Se borraran los modelos descargados, los certificados y ./data (token de Spotify). Continuar? [s/N] " r
  case "${r:-N}" in s|S|si|SI) ;; *) echo "Cancelado."; exit 0 ;; esac
  docker compose down --volumes --remove-orphans
  rm -rf data
  echo "ARIA eliminada por completo (el archivo .env se conserva; borralo a mano si quieres)."
else
  docker compose down --remove-orphans
  echo "Contenedores eliminados. Se conservan los volumenes (modelos, certificados) y ./data."
  echo "Usa ./uninstall.sh --purge para borrarlo todo."
fi
