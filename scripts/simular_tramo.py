# Se ejecuta dentro de «odoo shell» (lo lanza panel/jornada.sh):
#   docker exec -i furniture_odoo odoo shell -d furniture_db --no-http < scripts/simular_tramo.py
# Simula el tramo en curso y confirma la transacción solo si no hubo error.
# Si otro proceso de Odoo choca con el tramo (serialización), se repite entero.
import json
import time

from psycopg2 import errors as pg_errors

for intento in range(1, 4):
    try:
        resumen = env['odoo_crm.simulador'].sudo()._simular_tramo()  # noqa: F821 (env lo da odoo shell)
        env.cr.commit()  # noqa: F821
        break
    except (pg_errors.SerializationFailure, pg_errors.DeadlockDetected) as exc:
        env.cr.rollback()  # noqa: F821
        env.invalidate_all()  # noqa: F821
        print(f'SIMULADOR_REINTENTO={intento}: {exc}'.strip())
        time.sleep(5 * intento)
else:
    raise SystemExit('SIMULADOR: tres choques seguidos con otro proceso; se deja para el próximo tramo')
resumen['intentos'] = intento
print('SIMULADOR_RESUMEN=' + json.dumps(resumen, ensure_ascii=False, default=str))
print('SIMULADOR_INCIDENCIAS=%d' % len(resumen.get('incidencias', [])))
