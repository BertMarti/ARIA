#!/bin/sh
# Revisión de seguridad de ARIA (diaria). Solo analiza el código y una instancia de pruebas aislada (sin red):
# nunca toca producción, el router ni otros equipos.
#   1. Bandit (análisis estático de Python) comparado con la lista de falsos positivos ya revisados.
#   2. pip-audit: vulnerabilidades conocidas en las librerías que lleva la imagen de ARIA.
#   3. npm audit: dependencias de la app de Android.
#   4. Barreras de seguridad: tests/test_seguridad_rutas.py y el resto de pruebas de permisos.
# Deja un informe en Markdown y sale con 1 si hay algo NUEVO que mirar.
# Uso: herramientas/seguridad/revision.sh [carpeta_informes]   (por defecto data/seguridad)
set -u
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
SALIDA="${1:-$RAIZ/data/seguridad}"
DOCKER="${DOCKER:-docker}"
VENV="${ARIA_VENV_SEGURIDAD:-$HOME/.cache/aria-seguridad-venv}"
mkdir -p "$SALIDA"
FECHA=$(date +%F)
INFORME="$SALIDA/informe-$FECHA.md"
NUEVO=0
[ -x "$VENV/bin/bandit" ] || { python3 -m venv "$VENV" && "$VENV/bin/pip" install -q bandit pip-audit; }

{
echo "# Revisión de seguridad de ARIA — $FECHA"
echo
echo "## 1. Análisis estático (Bandit, severidad media o alta)"
"$VENV/bin/bandit" -q -r "$RAIZ/app/aria" "$RAIZ/app/escaner" "$RAIZ/app/descubre" "$RAIZ/sistema" -ll -f csv 2>/dev/null \
  | tail -n +2 | awk -F, '{print $1" | "$4" | "$7}' | sort > "$SALIDA/.bandit-hoy"
grep -v -F -f "$RAIZ/herramientas/seguridad/revisados.txt" "$SALIDA/.bandit-hoy" > "$SALIDA/.bandit-nuevo" || true
echo "Avisos: $(wc -l < "$SALIDA/.bandit-hoy"). Ya revisados (falsos positivos documentados): $(( $(wc -l < "$SALIDA/.bandit-hoy") - $(wc -l < "$SALIDA/.bandit-nuevo") ))."
if [ -s "$SALIDA/.bandit-nuevo" ]; then NUEVO=1; echo; echo "**Nuevos, hay que revisarlos:**"; sed 's/^/- /' "$SALIDA/.bandit-nuevo"; else echo "Nada nuevo."; fi
echo
echo "## 2. Librerías de Python (pip-audit)"
$DOCKER build -q -t aria-app:seguridad "$RAIZ/app" >/dev/null 2>&1
$DOCKER run --rm --entrypoint pip aria-app:seguridad freeze 2>/dev/null > "$SALIDA/.congelado"
if "$VENV/bin/pip-audit" -r "$SALIDA/.congelado" --no-deps --disable-pip --progress-spinner off > "$SALIDA/.pip-audit" 2>/dev/null; then
  echo "Sin vulnerabilidades conocidas ($(wc -l < "$SALIDA/.congelado") paquetes)."
else NUEVO=1; echo '```'; grep -v WARNING "$SALIDA/.pip-audit" | head -40; echo '```'; fi
echo
echo "## 3. App de Android (npm audit)"
if (cd "$RAIZ/movil/aria" && npm audit --omit=dev > "$SALIDA/.npm-audit" 2>&1); then echo "Sin vulnerabilidades."
else NUEVO=1; echo '```'; tail -20 "$SALIDA/.npm-audit"; echo '```'; fi
echo
echo "## 4. Barreras de seguridad (pruebas, en un contenedor sin red)"
printf 'FROM aria-app:seguridad\nUSER root\nRUN pip install -q pytest pytest-asyncio\n' | $DOCKER build -q -t aria-pytest:seguridad - >/dev/null 2>&1
RES=$($DOCKER run --rm --network none -v "$RAIZ":/src:ro --entrypoint sh aria-pytest:seguridad -c \
  'cp -r /src /tmp/t && cd /tmp/t/app && python -m pytest -q -p no:cacheprovider tests/test_seguridad_rutas.py tests/test_permisos.py tests/test_dispositivos_app.py tests/test_invitados.py tests/test_tele.py 2>&1 | tail -3')
echo '```'; echo "$RES"; echo '```'
echo "$RES" | grep -q "failed\|error" && NUEVO=1
echo
[ "$NUEVO" = 1 ] && echo "**Resultado: hay cosas NUEVAS que revisar.**" || echo "**Resultado: todo en orden.**"
} > "$INFORME"
rm -f "$SALIDA"/.bandit-hoy "$SALIDA"/.bandit-nuevo "$SALIDA"/.congelado "$SALIDA"/.pip-audit "$SALIDA"/.npm-audit
echo "Informe: $INFORME"
exit "$NUEVO"
