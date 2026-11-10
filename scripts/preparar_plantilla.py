# Se ejecuta dentro de «odoo shell» sobre la plantilla nueva (panel/plantilla_pruebas.sh):
#   docker exec -i furniture_odoo_pruebas odoo shell -d muebles_plantilla_nueva --no-http < este_fichero
# Deja la plantilla lista para clonar copias de prueba:
#   - neutralizada con la herramienta oficial de Odoo (sin tareas programadas ni
#     servidores de correo, y con el aviso de base de pruebas en la interfaz);
#   - con el usuario «probador»: ventas, compras, almacén y facturación, sin Ajustes.
import odoo.modules.neutralize

odoo.modules.neutralize.neutralize_database(env.cr)  # noqa: F821 (env lo da odoo shell)

GRUPOS = ('base.group_user', 'sales_team.group_sale_manager', 'purchase.group_purchase_manager',
          'stock.group_stock_manager', 'account.group_account_manager')
Usuarios = env['res.users'].with_context(no_reset_password=True, active_test=False)  # noqa: F821
probador = Usuarios.search([('login', '=', 'probador')], limit=1)
if not probador:
    probador = Usuarios.create({'login': 'probador', 'name': 'Probador (tu copia)',
                                'email': 'probador@mueblesdelhogar.example'})
campo = 'group_ids' if 'group_ids' in Usuarios._fields else 'groups_id'
grupos = [env.ref(x).id for x in GRUPOS if env.ref(x, raise_if_not_found=False)]  # noqa: F821
probador.write({'active': True, campo: [(6, 0, grupos)]})
env['ir.cron'].with_context(active_test=False).search([]).write({'active': False})  # noqa: F821
env.cr.commit()  # noqa: F821
print('PLANTILLA_OK probador=%d sistema=%s' % (probador.id, probador.has_group('base.group_system')))
