#!/usr/bin/env bash
# Instala (o actualiza) todo el homelab en esta máquina: SHIELD-DNS, HEIMDALL y ARIA.
#
#   curl -fsSL https://raw.githubusercontent.com/BertMarti/ARIA/main/instalar-todo.sh | bash
#   o, con el repo ya clonado:  ./instalar-todo.sh
#
# Opciones (variables de entorno):
#   HOMELAB_DIR=~/homelab        carpeta donde se clonan los tres proyectos
#   SOLO="SHIELD-DNS ARIA"       instalar solo algunos
#   COPIAS_AUTOMATICAS=1         programar una copia de seguridad diaria a las 04:30
set -euo pipefail

HOMELAB_DIR="${HOMELAB_DIR:-$HOME/homelab}"
PROYECTOS="${SOLO:-SHIELD-DNS HEIMDALL ARIA}"   # este orden importa: ARIA y HEIMDALL detectan a SHIELD-DNS

info()  { printf '\n\033[1;36m══ %s\033[0m\n' "$*"; }
ok()    { printf '\033[1;32m✔\033[0m  %s\n' "$*"; }
fallo() { printf '\033[1;31m✘\033[0m  %s\n' "$*" >&2; exit 1; }

command -v git >/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq git; }
if ! command -v docker >/dev/null 2>&1; then
  info "Instalando Docker (script oficial get.docker.com)"
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER" || true
fi
mkdir -p "$HOMELAB_DIR"

for p in $PROYECTOS; do
  info "$p"
  if [ -d "$HOMELAB_DIR/$p/.git" ]; then
    git -C "$HOMELAB_DIR/$p" pull --ff-only -q && ok "Repositorio actualizado"
  else
    git clone -q "https://github.com/BertMarti/$p.git" "$HOMELAB_DIR/$p" && ok "Repositorio clonado"
  fi
  (cd "$HOMELAB_DIR/$p" && ./install.sh) || fallo "La instalación de $p ha fallado. Revisa el mensaje de arriba."
done

if [ "${COPIAS_AUTOMATICAS:-0}" = "1" ]; then
  LINEA="30 4 * * * for p in SHIELD-DNS HEIMDALL ARIA; do [ -x $HOMELAB_DIR/\$p/backup.sh ] && $HOMELAB_DIR/\$p/backup.sh >> $HOMELAB_DIR/copias.log 2>&1; done # homelab-copias"
  ( crontab -l 2>/dev/null | grep -v '# homelab-copias' ; echo "$LINEA" ) | crontab -
  ok "Copia de seguridad diaria programada a las 04:30 (registro en $HOMELAB_DIR/copias.log)"
fi

IP="$(hostname -I | awk '{print $1}')"
cat <<EOF

════════════════════════════════════════════════════════
 Homelab listo. Entra en ARIA, tu panel central:

   https://${IP}

 Desde la página de Inicio de ARIA tienes acceso con un clic
 al bloqueador (SHIELD-DNS) y a la VPN (HEIMDALL).
 Las contraseñas están en el archivo .env de cada carpeta de
 ${HOMELAB_DIR}.
════════════════════════════════════════════════════════
EOF
