# -*- coding: utf-8 -*-
"""IVA español del 21 % en la demo (T-041). Se ejecuta con `odoo shell`.

Hasta ahora los 80 muebles, los pedidos de venta y los de compra llevaban el
impuesto genérico del 15 % que trae el plan contable de ejemplo de Odoo. Aquí:

0. El país fiscal de la compañía era EE. UU. (heredado del plan contable de
   ejemplo) en una empresa de Castellón: pasa a España, y con él los impuestos
   y grupos de impuestos de la compañía, porque Odoo exige que coincidan.
1. Se usan (o crean) los impuestos «IVA 21 %» de venta y de compra y se les da
   un grupo de impuestos propio, «IVA 21 %» (los de la v1 colgaban de «Tax 15 %»).
2. Los productos que llevaban el 15 % pasan al 21 % (venta y compra).
3. Las líneas de pedidos de venta y de compra con el 15 % que aún no se han
   facturado pasan al 21 %. No hay facturas en la demo: nada contabilizado se toca.
4. Los impuestos del 15 % se archivan para que nadie los elija por error.
5. Prueba dentro de una transacción que se deshace: un presupuesto, una
   compra y una factura de prueba calculan el 21 %.

Idempotente: ejecutarlo dos veces no cambia nada la segunda.
Imprime IVA_OK al final si todo cuadra.
"""
informe = []


def anota(texto):
    informe.append(texto)
    print('  ' + texto)


compania = env.company
Impuesto = env['account.tax'].with_context(active_test=False)
Grupo = env['account.tax.group']
tasa = 21.0


def buscar_impuesto(uso, importe):
    return Impuesto.search([
        ('type_tax_use', '=', uso), ('amount_type', '=', 'percent'),
        ('amount', '=', importe), ('company_id', '=', compania.id)], limit=1)


# 0. País fiscal ---------------------------------------------------------------
espana = env.ref('base.es')
if compania.account_fiscal_country_id != espana:
    compania.account_fiscal_country_id = espana
    anota('país fiscal de la compañía: España')
todos = Impuesto.search([('company_id', '=', compania.id), ('country_id', '!=', espana.id)])
if todos:
    todos.write({'country_id': espana.id})
    anota('%d impuestos pasan a país España' % len(todos))
grupos_viejos = Grupo.search([('country_id', '!=', espana.id)])
if grupos_viejos:
    grupos_viejos.write({'country_id': espana.id})
    anota('%d grupos de impuestos pasan a país España' % len(grupos_viejos))

# 1. Impuestos y grupo propio -------------------------------------------------
grupo = Grupo.search([('name', '=', 'IVA 21 %')], limit=1)
if not grupo:
    grupo = Grupo.create({'name': 'IVA 21 %', 'country_id': espana.id})
    anota('grupo de impuestos «IVA 21 %» creado')

nuevo = {}
for uso, nombre in (('sale', 'IVA 21 %'), ('purchase', 'IVA soportado 21 %')):
    impuesto = buscar_impuesto(uso, tasa)
    if not impuesto:
        impuesto = Impuesto.create({
            'name': nombre, 'amount': tasa, 'amount_type': 'percent',
            'type_tax_use': uso, 'company_id': compania.id,
            'tax_group_id': grupo.id})
        anota('impuesto %s creado' % nombre)
    cambios = {}
    if impuesto.tax_group_id != grupo:
        cambios['tax_group_id'] = grupo.id
    if impuesto.name != nombre:
        cambios['name'] = nombre
    if not impuesto.active:
        cambios['active'] = True
    if cambios:
        impuesto.write(cambios)
        anota('impuesto %s ajustado: %s' % (nombre, ', '.join(sorted(cambios))))
    nuevo[uso] = impuesto

# 2. Productos -----------------------------------------------------------------
viejo = {uso: buscar_impuesto(uso, 15.0) for uso in ('sale', 'purchase')}
Producto = env['product.template'].with_context(active_test=False)
if viejo['sale']:
    productos = Producto.search([('taxes_id', 'in', viejo['sale'].ids)])
    productos.write({'taxes_id': [(3, viejo['sale'].id), (4, nuevo['sale'].id)]})
    anota('%d productos: IVA de venta 15 %% -> 21 %%' % len(productos))
if viejo['purchase']:
    productos = Producto.search([('supplier_taxes_id', 'in', viejo['purchase'].ids)])
    productos.write({'supplier_taxes_id': [(3, viejo['purchase'].id), (4, nuevo['purchase'].id)]})
    anota('%d productos: IVA de compra 15 %% -> 21 %%' % len(productos))

# 3. Líneas de pedidos aún sin facturar -----------------------------------------
if viejo['sale']:
    lineas = env['sale.order.line'].search([
        ('tax_ids', 'in', viejo['sale'].ids), ('invoice_status', '!=', 'invoiced')])
    lineas.write({'tax_ids': [(3, viejo['sale'].id), (4, nuevo['sale'].id)]})
    anota('%d líneas de venta: 15 %% -> 21 %%' % len(lineas))
if viejo['purchase']:
    lineas = env['purchase.order.line'].search([
        ('tax_ids', 'in', viejo['purchase'].ids)])
    lineas = lineas.filtered(lambda l: l.qty_invoiced == 0)
    lineas.write({'tax_ids': [(3, viejo['purchase'].id), (4, nuevo['purchase'].id)]})
    anota('%d líneas de compra: 15 %% -> 21 %%' % len(lineas))

# 4. Archivar los del 15 % ------------------------------------------------------
for uso, impuesto in viejo.items():
    if impuesto and impuesto.active:
        impuesto.active = False
        anota('impuesto %s archivado' % impuesto.display_name)


# 5. Prueba en una transacción que se deshace ----------------------------------
class _Deshacer(Exception):
    pass


def comprobar():
    plantilla = env['product.template'].search([('is_furniture', '=', True)], limit=1)
    producto = plantilla.product_variant_id
    assert nuevo['sale'] in plantilla.taxes_id, 'el producto no lleva el IVA de venta 21 %'
    assert nuevo['purchase'] in plantilla.supplier_taxes_id, 'el producto no lleva el IVA de compra 21 %'
    cliente = env['res.partner'].search([('customer_rank', '>', 0)], limit=1)
    proveedor = env['res.partner'].search([('supplier_rank', '>', 0)], limit=1)
    venta = env['sale.order'].create({
        'partner_id': cliente.id,
        'order_line': [(0, 0, {'product_id': producto.id, 'product_uom_qty': 2, 'price_unit': 100.0})]})
    assert round(venta.amount_tax, 2) == 42.0, 'la venta no calcula el 21 %%: %s' % venta.amount_tax
    compra = env['purchase.order'].create({
        'partner_id': proveedor.id,
        'order_line': [(0, 0, {'product_id': producto.id, 'product_qty': 1, 'price_unit': 100.0})]})
    assert round(compra.amount_tax, 2) == 21.0, 'la compra no calcula el 21 %%: %s' % compra.amount_tax
    anota('prueba: presupuesto (200 EUR) = 42 EUR de IVA y compra (100 EUR) = 21 EUR de IVA')
    try:
        with env.cr.savepoint():
            venta.action_confirm()
            factura = venta._create_invoices()
            assert round(factura.amount_tax, 2) == 42.0, 'la factura no calcula el 21 %%: %s' % factura.amount_tax
            anota('prueba: la factura de esa venta lleva 42 EUR de IVA (21 %)')
            raise _Deshacer()
    except _Deshacer:
        pass


try:
    with env.cr.savepoint():
        comprobar()
        raise _Deshacer()
except _Deshacer:
    pass

env.cr.commit()
anota('IVA_OK')
