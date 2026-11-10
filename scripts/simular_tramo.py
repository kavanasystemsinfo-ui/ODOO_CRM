# Se ejecuta dentro de «odoo shell» (lo lanza panel/jornada.sh):
#   docker exec -i furniture_odoo odoo shell -d furniture_db --no-http < scripts/simular_tramo.py
# Simula el tramo en curso y confirma la transacción solo si no hubo error.
import json

resumen = env['odoo_crm.simulador'].sudo()._simular_tramo()  # noqa: F821 (env lo da odoo shell)
env.cr.commit()  # noqa: F821
print('SIMULADOR_RESUMEN=' + json.dumps(resumen, ensure_ascii=False, default=str))
print('SIMULADOR_INCIDENCIAS=%d' % len(resumen.get('incidencias', [])))
