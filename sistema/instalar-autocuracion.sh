#!/usr/bin/env bash
# Autocuración de la Raspberry Pi (idempotente). Uso: sudo ./sistema/instalar-autocuracion.sh
#  1. Autoheal: cada 2 minutos reinicia los contenedores Docker que estén "unhealthy"
#     (Docker reinicia los que se caen, pero no los que se quedan colgados).
#  2. Watchdog: si el sistema entero se bloquea, la Raspberry se reinicia sola (Raspberry Pi OS ya lo trae a 1 min).
set -euo pipefail
[ "$(id -u)" = 0 ] || exec sudo "$0" "$@"

cat > /usr/local/bin/homelab-autoheal <<'SH'
#!/bin/sh
# Reinicia los contenedores marcados como unhealthy y lo deja en el registro del sistema.
for c in $(docker ps --filter health=unhealthy --format '{{.Names}}'); do
  logger -t homelab-autoheal "Reiniciando $c (unhealthy)"
  docker restart "$c" >/dev/null 2>&1 || logger -t homelab-autoheal "No se pudo reiniciar $c"
done
SH
chmod 755 /usr/local/bin/homelab-autoheal

cat > /etc/systemd/system/homelab-autoheal.service <<'UNIT'
[Unit]
Description=Reinicia contenedores Docker colgados (unhealthy)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/homelab-autoheal
UNIT

cat > /etc/systemd/system/homelab-autoheal.timer <<'UNIT'
[Unit]
Description=Comprueba cada 2 minutos si hay contenedores colgados

[Timer]
OnBootSec=3min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now homelab-autoheal.timer >/dev/null
echo "✔ Autoheal activo (cada 2 min)"

if [ -e /dev/watchdog ]; then
  if [ "$(systemctl show -p RuntimeWatchdogUSec --value)" = "0" ]; then
    mkdir -p /etc/systemd/system.conf.d
    printf '[Manager]\nRuntimeWatchdogSec=1min\nRebootWatchdogSec=2min\n' > /etc/systemd/system.conf.d/50-homelab-watchdog.conf
    systemctl daemon-reexec
  fi
  echo "✔ Watchdog de hardware activo ($(systemctl show -p RuntimeWatchdogUSec --value)): si el sistema se bloquea, se reinicia solo"
else
  echo "! No hay /dev/watchdog: se omite el watchdog"
fi
