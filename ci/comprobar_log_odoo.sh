#!/usr/bin/env bash
# Falla si el log de Odoo tiene errores de carga o pruebas fallidas, o si las
# pruebas del módulo no llegaron a ejecutarse.
#   uso: ci/comprobar_log_odoo.sh <log> [exigir_pruebas]
set -euo pipefail
LOG="$1"
EXIGIR_PRUEBAS="${2:-no}"

if grep -E " (ERROR|CRITICAL) " "$LOG" | grep -v "werkzeug" ; then
  echo "::error::El log de Odoo tiene líneas ERROR/CRITICAL (arriba)."
  exit 1
fi
if grep -q "Traceback (most recent call last)" "$LOG"; then
  echo "::error::El log de Odoo tiene una traza de excepción."
  exit 1
fi
if [ "$EXIGIR_PRUEBAS" = "si" ]; then
  if ! grep -q "odoo.addons.ODOO_CRM.tests" "$LOG"; then
    echo "::error::No se ejecutó ninguna prueba del módulo ODOO_CRM."
    exit 1
  fi
  grep -E "[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests" "$LOG" || true
  if grep -E "[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests" "$LOG" | grep -vqE "(^|[^0-9])0 failed, 0 error\(s\)"; then
    echo "::error::Hay pruebas de Odoo fallidas."
    exit 1
  fi
fi
echo "Log de Odoo limpio."
