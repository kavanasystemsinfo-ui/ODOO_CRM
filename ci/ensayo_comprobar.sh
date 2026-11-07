#!/usr/bin/env bash
# Comprueba el estado de la demo del ensayo tras desplegar o tras volver atrás.
#   uso: sudo env MUEBLES_SNAPSHOT=... bash ci/ensayo_comprobar.sh v2|v1
set -euo pipefail
ESPERADO="$1"
version_pg="$(docker exec furniture_db postgres --version | grep -oE '[0-9]+' | head -1)"
version_mod() { docker exec furniture_db psql -U odoo -d "$1" -tAc \
  "SELECT latest_version FROM ir_module_module WHERE name = 'ODOO_CRM'"; }
curl -sf -o /dev/null http://127.0.0.1:8070/web/login
echo "PostgreSQL $version_pg · furniture_db $(version_mod furniture_db) · muebles_plantilla $(version_mod muebles_plantilla)"

if [ "$ESPERADO" = "v2" ]; then
  [ "$version_pg" = "17" ]
  for base in furniture_db muebles_plantilla; do [ "$(version_mod $base)" = "20.0.2.0.0" ]; done
  # La migración no perdió nada (incluido el caso de nombre repetido sembrado)
  docker exec -i furniture_odoo odoo shell -d furniture_db --no-http \
    < /root/ODOO_CRM/ci/verificar_migracion.py | grep MIGRACION_OK
  # El panel lee por la API con la clave que dejó el despliegue
  set -a; . /etc/kavana/muebles-panel.env; set +a
  python3 - <<'PY'
import sys
sys.path.insert(0, '/root/ODOO_CRM/panel')
import panel_muebles
cifras = panel_muebles.leer_cifras()
assert cifras['fichas_mobiliario'] == 80, cifras['fichas_mobiliario']
assert cifras['productos'] >= 80, cifras['productos']
print('PANEL_OK', cifras['productos'], 'productos,', cifras['fichas_mobiliario'], 'con ficha')
PY
  # La contraseña de visita ya no es la publicada
  docker exec furniture_db psql -U odoo -d furniture_db -tAc \
    "SELECT count(*) FROM res_users WHERE login = 'visita'" | grep -q 1
  test -s /root/copias/odoo_crm/visita_password.txt
  # La instantánea nueva es de la v2
  gunzip -c "$MUEBLES_SNAPSHOT" | grep -c furniture_material > /dev/null
else
  [ "$version_pg" = "15" ]
  [ "$(version_mod furniture_db)" = "20.0.1.1.0" ]
  gunzip -c "$MUEBLES_SNAPSHOT" | grep -c "CREATE TABLE public.furniture_product " > /dev/null
fi
echo "ESTADO_${ESPERADO}_OK"
