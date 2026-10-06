#!/usr/bin/env bash
# Instalador de ARIA (idempotente). Uso: ./install.sh   (SKIP_MODEL=1 para no descargar el modelo)
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
aviso() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
error() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. Docker ---
if ! command -v docker >/dev/null 2>&1; then
  aviso "Docker no está instalado."
  read -r -p "Instalarlo con el script oficial (https://get.docker.com)? [s/N] " resp
  case "${resp:-N}" in
    s|S|si|SI) curl -fsSL https://get.docker.com | sh
               sudo usermod -aG docker "$USER" || true
               aviso "Se ha añadido tu usuario al grupo docker: cierra sesión y vuelve a entrar, y relanza ./install.sh."
               exit 0 ;;
    *) error "Docker es necesario. Instalalo y vuelve a ejecutar ./install.sh" ;;
  esac
fi
docker compose version >/dev/null 2>&1 || error "Falta el plugin 'docker compose' (v2)."
docker info >/dev/null 2>&1 || error "No puedo hablar con Docker. Revisa que el servicio este activo y que tu usuario este en el grupo 'docker'."

# --- 2. .env ---
get_var() { grep -E "^$1=" .env | tail -n1 | cut -d= -f2-; }
set_var() { # set_var CLAVE VALOR  (los valores no contienen '|' ni saltos de linea)
  if grep -qE "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}

CREADO=0
if [ ! -f .env ]; then
  info "Creando .env con credenciales aleatorias"
  command -v openssl >/dev/null 2>&1 || error "Falta openssl (sudo apt install openssl)."
  cp .env.example .env
  chmod 600 .env
  IP="$(hostname -I | awk '{print $1}')"
  [ -n "$IP" ] || IP="127.0.0.1"
  set_var ARIA_PASSWORD "$(openssl rand -hex 12)"
  set_var ARIA_SECRET "$(openssl rand -hex 32)"
  set_var ARIA_LAN_IP "$IP"
  set_var ARIA_HOSTS "$IP,$(hostname).local,$(hostname),localhost"
  set_var SPOTIFY_REDIRECT_URI "https://$IP/spotify/callback"
  set_var ARIA_UID "$(id -u)"
  set_var ARIA_GID "$(id -g)"
  CREADO=1
else
  info ".env ya existe: se conserva"
fi
mkdir -p data

# Integraciones con SHIELD-DNS y HEIMDALL: si faltan, se rellenan desde sus .env
# (solo se lee con grep/cut; nunca se hace "source" de esos archivos).
leer_ajeno() { [ -f "$1" ] && grep -E "^$2=" "$1" | tail -n1 | cut -d= -f2- || true; }
rellenar() { # rellenar CLAVE VALOR: solo si la clave está vacía o no existe y hay valor
  if [ -z "$(get_var "$1")" ] && [ -n "$2" ]; then set_var "$1" "$2"; info "$1 rellenado automáticamente"; fi
}
IP_LAN="$(get_var ARIA_LAN_IP)"; IP_LAN="${IP_LAN:-127.0.0.1}"
rellenar SHIELD_URL "http://$IP_LAN:8080"
rellenar SHIELD_PASSWORD "$(leer_ajeno ../SHIELD-DNS/.env PIHOLE_PASSWORD)"
rellenar VPN_URL "https://$IP_LAN:51843"
rellenar VPN_USER "$(leer_ajeno ../HEIMDALL/.env WG_ADMIN_USER)"
rellenar VPN_PASSWORD "$(leer_ajeno ../HEIMDALL/.env WG_ADMIN_PASSWORD)"
[ -n "$(get_var SHIELD_PASSWORD)" ] || aviso "SHIELD_PASSWORD vacío: el Centro de control mostrará SHIELD-DNS como «no conectado» (ver README)."
[ -n "$(get_var VPN_PASSWORD)" ] || aviso "VPN_PASSWORD vacío: el Centro de control mostrará HEIMDALL como «no conectado» (ver README)."

# --- 3. Arranque ---
info "Construyendo y arrancando los contenedores"
docker compose up -d --build

info "Esperando a que los servicios estén sanos"
for c in aria-ollama aria-app aria-caddy; do
  for i in $(seq 1 60); do
    estado="$(docker inspect -f '{{.State.Health.Status}}' "$c" 2>/dev/null || echo desconocido)"
    [ "$estado" = "healthy" ] && break
    sleep 3
  done
  [ "$estado" = "healthy" ] || error "$c no está sano (estado: $estado). Mira: docker compose logs $c"
  info "$c: sano"
done

# --- 4. Modelo ---
MODEL="$(get_var ARIA_MODEL)"; MODEL="${MODEL:-llama3.2:3b}"
if [ "${SKIP_MODEL:-0}" = "1" ]; then
  aviso "SKIP_MODEL=1: no se descarga el modelo. Puedes hacerlo desde el panel de ARIA."
else
  info "Descargando el modelo $MODEL (puede tardar varios minutos)"
  docker compose exec -T ollama ollama pull "$MODEL"
fi

# --- 5. Resumen ---
IP="$(get_var ARIA_LAN_IP)"
echo
info "ARIA está lista"
echo "  URL:        https://$IP   (también https://$(hostname).local)"
echo "  Usuario:    $(get_var ARIA_USER)"
echo "  Contraseña: $(get_var ARIA_PASSWORD)   (guardada en $(pwd)/.env)"
echo "  El navegador avisará del certificado autofirmado: es lo esperado (ver README)."
