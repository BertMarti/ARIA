#!/usr/bin/env bash
# Activa la copia diaria cifrada fuera de la Pi (idempotente). Uso: ./sistema/instalar-copias.sh
#  - Crea la contraseña de cifrado (~/homelab/.clave-copias) si no existe y te la muestra UNA vez.
#  - Crea el repositorio PRIVADO <tu-usuario>/homelab-copias en GitHub si no existe (necesita `gh` autenticado).
#  - Instala el timer systemd homelab-copias (cada día a las 04:30) y hace una primera copia.
set -euo pipefail
cd "$(dirname "$0")"
HOMELAB_DIR="${HOMELAB_DIR:-$HOME/homelab}"
CLAVE="$HOMELAB_DIR/.clave-copias"
USUARIO_GH="$(gh api user -q .login)"
REPO="$USUARIO_GH/homelab-copias"

if [ ! -s "$CLAVE" ]; then
  umask 077
  openssl rand -base64 24 | tr -d '\n' > "$CLAVE"
  NUEVA=1
fi
chmod 600 "$CLAVE"

if ! gh repo view "$REPO" >/dev/null 2>&1; then
  gh repo create "$REPO" --private --description "Copias de seguridad cifradas del homelab (ARIA, HEIMDALL, SHIELD-DNS)" >/dev/null
  echo "✔ Repositorio privado $REPO creado"
fi
[ "$(gh repo view "$REPO" --json isPrivate -q .isPrivate)" = "true" ] || { echo "✘ $REPO no es privado: abortando"; exit 1; }

SCRIPT="$(cd .. && pwd)/sistema/copia-diaria.sh"
sudo tee /etc/systemd/system/homelab-copias.service >/dev/null <<UNIT
[Unit]
Description=Copia de seguridad diaria cifrada del homelab (a GitHub privado)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=$(id -un)
Environment=HOME=$HOME
Environment=HOMELAB_DIR=$HOMELAB_DIR
ExecStart=$SCRIPT
UNIT
sudo tee /etc/systemd/system/homelab-copias.timer >/dev/null <<'UNIT'
[Unit]
Description=Copia de seguridad diaria del homelab a las 04:30

[Timer]
OnCalendar=*-*-* 04:30:00
Persistent=true
RandomizedDelaySec=10min

[Install]
WantedBy=timers.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-copias.timer >/dev/null
echo "✔ Copia diaria programada (04:30). Registro: journalctl -t homelab-copias"

"$SCRIPT"

if [ "${NUEVA:-0}" = 1 ]; then
  cat <<EOF

════════════════════════════════════════════════════════════
 CONTRASEÑA DE TUS COPIAS (guárdala en tu gestor de contraseñas)
   $(cat "$CLAVE")
 Sin ella NO se pueden abrir las copias si la Raspberry se pierde.
════════════════════════════════════════════════════════════
EOF
fi
