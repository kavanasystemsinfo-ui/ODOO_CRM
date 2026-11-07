# Se ejecuta con `odoo shell` sobre la base limpia con ODOO_CRM instalado.
# Crea el usuario de integración del panel (solo el grupo de lectura del
# módulo), su API key y unos pocos datos de negocio cuyas cifras se conocen.
# Imprime ESPERADO=<json> y API_KEY=<clave> para el paso siguiente del CI.
import json
from datetime import timedelta

from odoo import fields

usuario = env['res.users'].create({
    'name': 'Integración panel del día',
    'login': 'panel_integracion',
    'group_ids': [(6, 0, [env.ref('base.group_user').id,
                          env.ref('ODOO_CRM.group_panel_lectura').id])],
})
# Odoo 20: la API JSON-2 exige scope 'rpc'; la duración máxima la marca el
# grupo del módulo (90 días), así que se pide como el propio usuario.
clave = env['res.users.apikeys'].with_user(usuario)._generate(
    'rpc', 'panel del día (CI)', fields.Datetime.now() + timedelta(days=60))

raiz = env.ref('ODOO_CRM.categoria_muebles_hogar')
mesas = env['product.category'].create({'name': 'Mesas', 'parent_id': raiz.id})
mesa = env['product.template'].create({
    'name': 'Mesa Turia', 'categ_id': mesas.id, 'type': 'consu', 'is_storable': True,
    'list_price': 500.0, 'standard_price': 200.0, 'is_published': True,
    'furniture_material': 'Roble', 'furniture_style': 'Nórdico',
    'furniture_warranty_months': 24,
})
silla = env['product.template'].create({
    'name': 'Silla Albufera', 'categ_id': mesas.id, 'type': 'consu', 'is_storable': True,
    'list_price': 90.0, 'standard_price': 30.0, 'furniture_material': 'Haya',
})
existencias = env.ref('stock.warehouse0').lot_stock_id
for producto, cantidad in ((mesa, 4), (silla, 10)):
    env['stock.quant'].create({
        'product_id': producto.product_variant_id.id,
        'location_id': existencias.id,
        'inventory_quantity': cantidad,
    }).action_apply_inventory()

cliente = env['res.partner'].create({'name': 'Hotel Ruzafa', 'email': 'compras@hotelruzafa.es'})
confirmado = env['sale.order'].create({
    'partner_id': cliente.id,
    'order_line': [(0, 0, {'product_id': mesa.product_variant_id.id, 'product_uom_qty': 1})],
})
confirmado.action_confirm()
env['sale.order'].create({
    'partner_id': cliente.id,
    'order_line': [(0, 0, {'product_id': silla.product_variant_id.id, 'product_uom_qty': 6})],
})
lead = env['crm.lead'].create({
    'name': 'Reforma Hotel Ruzafa', 'type': 'opportunity', 'partner_id': cliente.id,
    'x_es_contrato': True, 'x_muestra_pedida': True,
})
lead.message_post(body='Le envío el catálogo', message_type='comment',
                  subtype_xmlid='mail.mt_comment')
env.cr.commit()
env.invalidate_all()

dominio_internas = [('location_id.usage', '=', 'internal'), ('quantity', '>', 0)]
quants = env['stock.quant'].search(dominio_internas)
esperado = {
    'productos': env['product.template'].search_count([('active', '=', True)]),
    'publicados': env['product.template'].search_count([('is_published', '=', True)]),
    'fichas_mobiliario': env['product.template'].search_count([('furniture_material', '!=', False)]),
    'clientes': env['res.partner'].search_count([('customer_rank', '>', 0)]),
    'pedidos': env['sale.order'].search_count([]),
    'confirmados': env['sale.order'].search_count([('state', '=', 'sale')]),
    'presupuestos': env['sale.order'].search_count([('state', 'in', ['draft', 'sent'])]),
    'entregas_pendientes': env['stock.picking'].search_count([
        ('picking_type_id.code', '=', 'outgoing'),
        ('state', 'in', ['assigned', 'waiting', 'confirmed'])]),
    'unidades': int(sum(quants.mapped('quantity'))),
    'referencias': len(quants.product_id),
    'valor_almacen': round(sum(q.quantity * q.product_id.standard_price for q in quants), 2),
    'lead_id': lead.id,
    'lead_score': lead.x_score_kavana,
}
print('ESPERADO=' + json.dumps(esperado))
print('API_KEY=' + clave)
