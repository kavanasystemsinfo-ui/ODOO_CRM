# Se ejecuta con `odoo shell` sobre una base con el módulo en su versión 1.
# Reproduce el estado del laboratorio público antes de la v2: la categoría
# «Muebles de Hogar» creada a mano (sin identificador externo) y un producto
# nativo por cada ficha del catálogo paralelo, con el mismo nombre.
raiz = env['product.category'].create({'name': 'Muebles de Hogar'})
fichas = env['furniture.product'].search([])
assert fichas, 'la v1 debería traer las fichas del catálogo paralelo'
for ficha in fichas:
    env['product.template'].create({
        'name': ficha.name,
        'categ_id': raiz.id,
        'list_price': ficha.list_price,
        'standard_price': ficha.standard_price,
    })
# Caso ambiguo a propósito: una segunda ficha con el nombre de la primera.
# La migración debe quedarse con la más antigua y avisar en el log.
primera = fichas.sorted('id')[0]
primera.copy({'name': primera.name, 'material': 'MATERIAL DE LA FICHA DUPLICADA'})
env.cr.commit()
print('SIEMBRA_V1_OK', len(fichas), '| ficha duplicada:', primera.name, '| material esperado:', primera.material)
