#!/bin/sh
# ARIA de demostración con datos INVENTADOS (para capturas del README y pruebas visuales).
# Uso: herramientas/demo/arrancar.sh [--sembrar]      → http://127.0.0.1:18080 (usuario «demo»)
#      herramientas/demo/arrancar.sh --parar
# Todo queda en herramientas/demo/.demo/ (no se sube a git). La contraseña está en .demo/demo.env.
set -e
AQUI=$(cd "$(dirname "$0")" && pwd)
RAIZ=$(cd "$AQUI/../.." && pwd)
DATOS=${ARIA_DEMO_DIR:-$AQUI/.demo}
DOCKER=${DOCKER:-docker}
if [ "$1" = "--parar" ]; then $DOCKER rm -f aria-demo >/dev/null 2>&1 || true; echo "Demo parada."; exit 0; fi
mkdir -p "$DATOS/data"
if [ ! -f "$DATOS/demo.env" ]; then
  cat > "$DATOS/demo.env" <<FIN
ARIA_USER=demo
ARIA_PASSWORD=$(head -c 15 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 20)
ARIA_SECRET=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40)
ARIA_NOMBRE_USUARIO=Ana
ARIA_LAN_IP=192.168.1.50
ARIA_HOSTS=localhost,127.0.0.1
ARIA_RED_PERMITIDA=192.168.1.0/24
ARIA_ROUTER_IP=192.168.1.1
ARIA_CIUDAD=Madrid
ARIA_LAT=40.4168
ARIA_LON=-3.7038
ARIA_TZ=Europe/Madrid
ARIA_MODULOS=-
ARIA_DATA_DIR=/data
ARIA_ESCANER_DIR=/data/escaner
FIN
  chmod 600 "$DATOS/demo.env"
fi
$DOCKER build -q -t aria-app:demo "$RAIZ/app" >/dev/null
$DOCKER rm -f aria-demo >/dev/null 2>&1 || true
$DOCKER run -d --name aria-demo --env-file "$DATOS/demo.env" -p 127.0.0.1:18080:8000 \
  -v "$DATOS/data:/data" -v "$AQUI:/demo:ro" aria-app:demo \
  uvicorn aria.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*' --no-server-header >/dev/null
$DOCKER exec -d aria-demo python /demo/telemetria_falsa.py
sleep 4
if [ "$1" = "--sembrar" ]; then $DOCKER exec -w /srv -e PYTHONPATH=/srv aria-demo python /demo/sembrar.py; fi
echo "Demo en http://127.0.0.1:18080 (usuario demo; contraseña en $DATOS/demo.env)"
