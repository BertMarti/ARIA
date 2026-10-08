#!/usr/bin/env bash
# Instala el agente mínimo de ARIA en el sistema (telemetría por contenedor y reinicio bajo petición firmada).
# Uso: ./sistema/instalar-host-agente.sh   (idempotente; pide sudo)
set -euo pipefail
cd "$(dirname "$0")/.."
ARIA_DIR="$(pwd)"
sudo tee /etc/systemd/system/aria-host-agente.service >/dev/null <<UNIT
[Unit]
Description=Agente de ARIA en el sistema (telemetría y reinicio bajo petición firmada)
After=docker.service
Wants=docker.service

[Service]
Environment=ARIA_DIR=$ARIA_DIR
ExecStart=/usr/bin/python3 $ARIA_DIR/sistema/host-agente.py
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectHome=read-only
ReadWritePaths=$ARIA_DIR/data/host
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
UNIT
mkdir -p "$ARIA_DIR/data/host/peticiones"
sudo systemctl daemon-reload
sudo systemctl enable --now aria-host-agente.service
sudo systemctl restart aria-host-agente.service
echo "✔ aria-host-agente activo (journalctl -u aria-host-agente)"
