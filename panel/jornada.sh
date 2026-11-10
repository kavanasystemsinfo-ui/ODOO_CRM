#!/bin/bash
# Un tramo de la jornada de la empresa simulada, de principio a fin.
#
#   1. Si un visitante ha tocado la demo, se restaura antes (su rastro no se
#      queda en la historia de la empresa).
#   2. Odoo simula el tramo (models/simulador_empresa.py) y confirma.
#   3. El estado resultante pasa a ser la instantánea canónica, con sus
#      recuentos: la limpieza de cada media hora compara ya contra él.
#   4. Se borra la caché del panel para que enseñe las cifras nuevas.
#
# Comparte cerrojo con limpieza_automatica.sh: nunca restauran y simulan a la vez.
# Lo lanza muebles-jornada.timer. Bajo systemd escribe en el journal.

set -uo pipefail

CARPETA="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$CARPETA")"
PY="${PY:-/usr/bin/python3}"
DOCKER="${MUEBLES_DOCKER:-/usr/bin/docker}"
ODOO="${MUEBLES_ODOO_CONTAINER:-furniture_odoo}"
BASE="${MUEBLES_DB:-furniture_db}"
CERROJO="${MUEBLES_CERROJO:-/run/muebles-laboratorio.lock}"

exec 9>"$CERROJO"
flock -w 900 9 || { echo "otra operación del laboratorio sigue en marcha"; exit 1; }

if ! "$PY" "$CARPETA/demo_restaurar_muebles.py" --verificar > /dev/null 2>&1; then
  echo "$(date -Is) la demo no cuadra con la instantánea: restaurando antes de simular"
  "$PY" "$CARPETA/demo_restaurar_muebles.py" --restaurar --sin-refrescar-panel || exit 1
fi

SALIDA="$("$DOCKER" exec -i "$ODOO" odoo shell -d "$BASE" --no-http < "$REPO/scripts/simular_tramo.py" 2>&1)"
RESUMEN="$(printf '%s\n' "$SALIDA" | sed -n 's/^SIMULADOR_RESUMEN=//p')"
if [ -z "$RESUMEN" ]; then
  echo "$(date -Is) el simulador falló; la base queda como estaba"
  printf '%s\n' "$SALIDA" | tail -25
  exit 1
fi
echo "$(date -Is) tramo: $RESUMEN"

case "$RESUMEN" in
  *'"omitido"'*) exit 0 ;;  # fuera de horario o ya simulado: nada que fijar
esac

"$PY" "$CARPETA/demo_restaurar_muebles.py" --fijar-instantanea || exit 1
CACHE="${MUEBLES_PANEL_CACHE:-$CARPETA/cache_panel}"
rm -f "$CACHE"/dia_*.json

INCIDENCIAS="$(printf '%s\n' "$SALIDA" | sed -n 's/^SIMULADOR_INCIDENCIAS=//p')"
if [ "${INCIDENCIAS:-0}" != "0" ]; then
  echo "$(date -Is) tramo con $INCIDENCIAS incidencias (ver resumen); el resto quedó guardado"
  exit 2
fi
