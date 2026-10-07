#!/usr/bin/env bash
# Publica ARIA, SHIELD-DNS y HEIMDALL en tu dominio con Cloudflare Tunnel + Access.
# Idempotente: crea solo lo que falte. Uso: ./cloudflare/configurar.sh
# Necesita ~/homelab/cloudflare.env con CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, DOMINIO y EMAIL_ACCESO
# (el token necesita: Zone·DNS·Edit, Account·Cloudflare Tunnel·Edit, Account·Access: Apps and Policies·Edit).
set -euo pipefail
cd "$(dirname "$0")"
ENVF="${CLOUDFLARE_ENV:-$HOME/homelab/cloudflare.env}"
[ -f "$ENVF" ] || { echo "Falta $ENVF (ver README → Acceso desde fuera)"; exit 1; }
set -a; . "$ENVF"; set +a
: "${CLOUDFLARE_API_TOKEN:?}" "${CLOUDFLARE_ACCOUNT_ID:?}" "${DOMINIO:?}" "${EMAIL_ACCESO:?}"
LAN_IP="${LAN_IP:-$(hostname -I | awk '{print $1}')}"
H="Authorization: Bearer $CLOUDFLARE_API_TOKEN"; J='Content-Type: application/json'
A="https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID"
cf() { curl -fsS "$@" -H "$H"; }
jq_py() { python3 -c "import sys,json; d=json.load(sys.stdin); $1"; }
guardar() { umask 077; if grep -q "^$1=" "$ENVF"; then sed -i "s|^$1=.*|$1=$2|" "$ENVF"; else echo "$1=$2" >> "$ENVF"; fi; }

ZONA=$(cf "https://api.cloudflare.com/client/v4/zones?name=$DOMINIO" | jq_py "print(d['result'][0]['id'])")
guardar CLOUDFLARE_ZONE_ID "$ZONA"

# 1. Túnel
TID=$(cf "$A/cfd_tunnel?is_deleted=false&name=homelab" | jq_py "r=d['result'];print(r[0]['id'] if r else '')")
[ -n "$TID" ] || TID=$(cf -X POST "$A/cfd_tunnel" -H "$J" -d '{"name":"homelab","config_src":"cloudflare"}' | jq_py "print(d['result']['id'])")
guardar CLOUDFLARE_TUNNEL_ID "$TID"
guardar CLOUDFLARE_TUNNEL_TOKEN "$(cf "$A/cfd_tunnel/$TID/token" | jq_py "print(d['result'])")"
echo "✔ Túnel homelab"

# 2. Qué publica cada nombre
python3 - "$DOMINIO" "$LAN_IP" > /tmp/cf-ingress.json <<'PY'
import json,sys; d,ip=sys.argv[1:3]
print(json.dumps({"config":{"ingress":[
 {"hostname":f"aria.{d}","service":"http://app:8000"},
 {"hostname":f"shield.{d}","service":f"http://{ip}:8080"},
 {"hostname":f"heimdall.{d}","service":f"https://{ip}:51843","originRequest":{"noTLSVerify":True,"httpHostHeader":ip}},
 {"service":"http_status:404"}]}}))
PY
cf -X PUT "$A/cfd_tunnel/$TID/configurations" -H "$J" --data @/tmp/cf-ingress.json >/dev/null; rm -f /tmp/cf-ingress.json
echo "✔ Rutas: aria., shield. y heimdall.$DOMINIO"

# 3. Protección (Access) ANTES de publicar nada
INC=$(python3 -c "import os,json;print(json.dumps([{'email':{'email':e.strip()}} for e in os.environ['EMAIL_ACCESO'].split(',') if e.strip()]))")
EXISTEN=$(cf "$A/access/apps" | jq_py "print(' '.join(a['domain'] for a in d['result']))")
for par in "ARIA:aria" "SHIELD-DNS · Pi-hole:shield" "HEIMDALL · VPN:heimdall"; do
  N=${par%%:*}; S=${par##*:}; DOM="$S.$DOMINIO"
  case " $EXISTEN " in *" $DOM "*) echo "✔ $DOM ya protegido"; continue;; esac
  BODY=$(python3 -c "import json,sys;print(json.dumps({'type':'self_hosted','name':sys.argv[1],'domain':sys.argv[2],'session_duration':'720h','app_launcher_visible':True,'policies':[{'name':'Propietario','decision':'allow','include':json.loads(sys.argv[3])}]}))" "$N" "$DOM" "$INC")
  cf -X POST "$A/access/apps" -H "$J" -d "$BODY" >/dev/null && echo "✔ $DOM protegido (solo $EMAIL_ACCESO)"
done

# 4. Nombres DNS hacia el túnel
for S in aria shield heimdall; do
  N=$(cf "https://api.cloudflare.com/client/v4/zones/$ZONA/dns_records?name=$S.$DOMINIO" | jq_py "print(len(d['result']))")
  [ "$N" = 0 ] && cf -X POST "https://api.cloudflare.com/client/v4/zones/$ZONA/dns_records" -H "$J" \
    -d "{\"type\":\"CNAME\",\"name\":\"$S\",\"content\":\"$TID.cfargotunnel.com\",\"proxied\":true}" >/dev/null
  echo "✔ https://$S.$DOMINIO"
done

# 5. Conector en la Raspberry
docker compose --env-file "$ENVF" up -d
echo
echo "Listo. Entra en https://aria.$DOMINIO (Cloudflare te pedirá un código por email)."
echo "Si la pantalla de acceso solo ofrece «Cloudflare», añade en Zero Trust → Integrations →"
echo "Identity providers → Add → One-time PIN (código por email)."
