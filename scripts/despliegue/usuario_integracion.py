# Se ejecuta con `odoo shell -d <base>`. Crea (o reutiliza) el usuario de
# integración del panel del día y le genera una API key nueva:
#   - grupos: Usuario interno + «Panel del día: solo lectura» (y nada más);
#   - clave con alcance 'rpc' (el que exige la API JSON-2 de Odoo 20) que
#     caduca a los DIAS_CLAVE días (el grupo permite como mucho 90);
#   - revoca las claves anteriores del panel, así rotar es volver a ejecutarlo.
# Imprime una sola línea API_KEY=<clave>; quien lo llama la guarda en el
# entorno del panel y no la escribe en ningún otro sitio.
import os
from datetime import timedelta

from odoo import fields

LOGIN = 'panel_integracion'
NOMBRE_CLAVE = 'panel del día'
DIAS_CLAVE = int(os.environ.get('DIAS_CLAVE', '85'))

grupos = [env.ref('base.group_user').id, env.ref('ODOO_CRM.group_panel_lectura').id]
usuario = env['res.users'].with_context(active_test=False).search([('login', '=', LOGIN)], limit=1)
if usuario:
    usuario.write({'active': True, 'group_ids': [(6, 0, grupos)]})
else:
    usuario = env['res.users'].create({
        'name': 'Integración panel del día',
        'login': LOGIN,
        'group_ids': [(6, 0, grupos)],
    })

claves = env['res.users.apikeys'].sudo()
anteriores = claves.search([('user_id', '=', usuario.id), ('name', '=', NOMBRE_CLAVE)])
anteriores._remove()
clave = claves.with_user(usuario).sudo(False)._generate(
    'rpc', NOMBRE_CLAVE, fields.Datetime.now() + timedelta(days=DIAS_CLAVE))
env.cr.commit()
print(f'INTEGRACION_OK usuario={usuario.id} claves_revocadas={len(anteriores)} '
      f'caduca_en_dias={DIAS_CLAVE}')
print('API_KEY=' + clave)
