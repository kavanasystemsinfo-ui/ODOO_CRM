# Se ejecuta con `odoo shell` tras actualizar el módulo a la v2.
# Comprueba que la migración no perdió nada y no duplicó la categoría.
errores = []

if 'furniture.product' in env.registry:
    errores.append('el modelo furniture.product sigue cargado')

env.cr.execute("SELECT to_regclass('furniture_product_v1_backup') IS NOT NULL")
if not env.cr.fetchone()[0]:
    errores.append('no existe la copia furniture_product_v1_backup')

env.cr.execute('SELECT count(*), count(material) FROM furniture_product_v1_backup')
total_v1, con_material_v1 = env.cr.fetchone()

con_ficha = env['product.template'].search_count([('furniture_material', '!=', False)])
if con_ficha != con_material_v1:
    errores.append(f'{con_ficha} productos con material; se esperaban {con_material_v1}')

raices = env['product.category'].search_count(
    [('name', '=', 'Muebles de Hogar'), ('parent_id', '=', False)])
if raices != 1:
    errores.append(f'{raices} categorías raíz «Muebles de Hogar»; se esperaba 1')

raiz = env.ref('ODOO_CRM.categoria_muebles_hogar', raise_if_not_found=False)
if not raiz:
    errores.append('la categoría raíz no quedó vinculada al identificador del módulo')

muebles = env['product.template'].search_count([('is_furniture', '=', True)])
if muebles != total_v1:
    errores.append(f'{muebles} productos marcados como mueble; se esperaban {total_v1}')

if errores:
    print('MIGRACION_FALLIDA')
    for error in errores:
        print(' -', error)
else:
    print('MIGRACION_OK', total_v1, 'fichas;', con_ficha, 'con material')
