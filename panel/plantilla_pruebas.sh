#!/bin/bash
# Renueva la plantilla de la que salen las copias de prueba por visitante.
#
# Parte de la instantánea canónica (la misma que restaura la demo), así que cada
# copia nueva enseña la empresa tal y como estaba en el último tramo simulado.
# Se construye con otro nombre y al final se cambia por la anterior: una copia
# que se esté creando justo entonces reintenta (controllers/pruebas.py).
#
# Debe ejecutarse con el cerrojo del laboratorio ya tomado (lo llama
# jornada.sh, o el despliegue). Como root.

set -uo pipefail

CARPETA="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$CARPETA")"
PY="${PY:-/usr/bin/python3}"
DOCKER="${MUEBLES_DOCKER:-/usr/bin/docker}"
BD="${MUEBLES_DB_CONTAINER:-furniture_db}"
ODOO_PRUEBAS="${MUEBLES_ODOO_PRUEBAS:-furniture_odoo_pruebas}"
FILESTORE="${MUEBLES_FILESTORE:-/var/lib/docker/volumes/odoo_crm_odoo_data/_data/filestore}"
ORIGEN="${MUEBLES_DB:-furniture_db}"
PLANTILLA=muebles_plantilla
NUEVA=muebles_plantilla_nueva
VIEJA=muebles_plantilla_vieja

psql() { "$DOCKER" exec -i "$BD" psql -v ON_ERROR_STOP=1 -q -U odoo "$@"; }
falla() { echo "$(date -Is) plantilla de pruebas: $*"; exit 1; }

INSTANTANEA="$(cd "$CARPETA" && "$PY" -c 'import configuracion; print(configuracion.snapshot())')"
[ -s "$INSTANTANEA" ] || falla "no hay instantánea en $INSTANTANEA"

psql -d postgres -c "DROP DATABASE IF EXISTS $NUEVA WITH (FORCE)" -c "CREATE DATABASE $NUEVA OWNER odoo" \
  || falla "no se pudo crear $NUEVA"
gzip -dc "$INSTANTANEA" | psql -d "$NUEVA" > /dev/null || falla "no se pudo cargar la instantánea"
psql -d "$NUEVA" -c "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%'" || falla "assets"
rm -rf "${FILESTORE:?}/$NUEVA"
if [ -d "$FILESTORE/$ORIGEN" ]; then cp -a "$FILESTORE/$ORIGEN" "$FILESTORE/$NUEVA"; fi

SALIDA="$("$DOCKER" exec -i "$ODOO_PRUEBAS" odoo shell -d "$NUEVA" --no-http < "$REPO/scripts/preparar_plantilla.py" 2>&1)"
printf '%s\n' "$SALIDA" | grep -q '^PLANTILLA_OK' || { printf '%s\n' "$SALIDA" | tail -15; falla "preparar_plantilla.py"; }

# Cambio: la nueva pasa a ser la plantilla. Si alguien está clonando la vieja
# justo ahora, el ALTER espera unos segundos y reintenta.
for intento in 1 2 3 4 5 6 7 8 9 10; do
  if ! psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$PLANTILLA'" | grep -q 1; then break; fi
  psql -d postgres -c "ALTER DATABASE $PLANTILLA RENAME TO $VIEJA" 2>/dev/null && break
  sleep 2
  [ "$intento" = 10 ] && falla "la plantilla anterior sigue en uso"
done
psql -d postgres -c "ALTER DATABASE $NUEVA RENAME TO $PLANTILLA" || falla "no se pudo activar la nueva plantilla"
psql -d postgres -c "DROP DATABASE IF EXISTS $VIEJA WITH (FORCE)"
rm -rf "${FILESTORE:?}/$VIEJA"
[ -d "$FILESTORE/$PLANTILLA" ] && mv "$FILESTORE/$PLANTILLA" "$FILESTORE/$VIEJA"
[ -d "$FILESTORE/$NUEVA" ] && mv "$FILESTORE/$NUEVA" "$FILESTORE/$PLANTILLA"
rm -rf "${FILESTORE:?}/$VIEJA"
echo "$(date -Is) plantilla de pruebas renovada ($(printf '%s\n' "$SALIDA" | grep '^PLANTILLA_OK'))"
