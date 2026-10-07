#!/usr/bin/env bash
# Actualiza ARIA (idempotente): código, imágenes base y contenedores.
# Uso: ./update.sh
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
aviso() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
error() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

docker compose version >/dev/null 2>&1 || error "Falta Docker Compose v2."
[ -f .env ] || error "No existe .env: ejecuta primero ./install.sh"

info "Descargando los últimos cambios (git pull --ff-only)"
git pull --ff-only || error "No se pudo avanzar en fast-forward. Revisa los cambios locales con 'git status'."

# Instalaciones anteriores a la búsqueda en internet: genera la clave interna de SearXNG si falta.
if ! grep -qE '^SEARXNG_SECRET=.+' .env; then
  command -v openssl >/dev/null 2>&1 || error "Falta openssl (sudo apt install openssl)."
  sed -i '/^SEARXNG_SECRET=/d' .env
  printf 'SEARXNG_SECRET=%s\n' "$(openssl rand -hex 32)" >> .env
  info "SEARXNG_SECRET generado"
fi

info "Actualizando las imágenes base (ollama, searxng, caddy)"
docker compose pull

info "Reconstruyendo y reiniciando los contenedores"
docker compose up -d --build --remove-orphans

info "Limpiando imágenes sin usar"
docker image prune -f >/dev/null

info "Esperando a que los servicios estén sanos"
for c in aria-ollama aria-searxng aria-app aria-caddy; do
  estado=desconocido
  for _ in $(seq 1 60); do
    estado="$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo desconocido)"
    [ "$estado" = "healthy" ] && break
    sleep 3
  done
  [ "$estado" = "healthy" ] || error "$c no está sano (estado: $estado). Mira: docker compose logs $c"
  info "$c: sano"
done

echo
docker compose ps
info "ARIA actualizada."
