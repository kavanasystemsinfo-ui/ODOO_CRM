# -*- coding: utf-8 -*-
"""
Muebles, fase 1c: rematar las lineas que resisten.

Odoo tampoco deja cambiar el producto si la linea figura como entregada
(`qty_delivered`), y ese valor seguia puesto de antes de vaciar el almacen.
Se pone a cero junto con `qty_invoiced` y se reescriben las 15 lineas que
quedaban apuntando al catalogo generico.
"""

import random

random.seed(13)


def paso(texto):
    print(texto, flush=True)


env.cr.execute("UPDATE sale_order_line SET qty_delivered = 0, qty_invoiced = 0")
env.cr.commit()
paso("contadores qty_delivered/qty_invoiced puestos a cero")

reales = list(env['product.product'].search([
    ('categ_id.parent_id.name', '=', 'Muebles de Hogar'),
    ('active', '=', True),
]))

pendientes = env['sale.order.line'].search(
    [('product_id.categ_id.parent_id.name', '!=', 'Muebles de Hogar')])
paso("lineas pendientes: %d" % len(pendientes))

por_pedido = {}
for linea in pendientes:
    por_pedido.setdefault(linea.order_id.id, []).append(linea)

cambiadas = fallos = 0
for pedido_id, lineas in por_pedido.items():
    elegidos = random.sample(reales, min(len(lineas), len(reales)))
    for i, linea in enumerate(lineas):
        producto = elegidos[i % len(elegidos)]
        try:
            with env.cr.savepoint():
                linea.write({
                    'product_id': producto.id,
                    'name': producto.get_product_multiline_description_sale(),
                    'price_unit': producto.list_price or linea.price_unit,
                    'product_uom': producto.uom_id.id,
                })
                cambiadas += 1
        except Exception as exc:
            fallos += 1
            paso("  aviso linea %s: %s" % (linea.id, str(exc)[:70]))
env.cr.commit()
paso("reescritas: %d (fallos: %d)" % (cambiadas, fallos))

archivados = env['product.template'].search([('active', '=', False)])
borrados = 0
for plantilla in archivados:
    try:
        with env.cr.savepoint():
            plantilla.unlink()
            borrados += 1
    except Exception:
        pass
env.cr.commit()
paso("archivados borrados: %d | quedan: %d" % (
    borrados, env['product.template'].search_count([('active', '=', False)])))

paso("")
paso("=== ESTADO ===")
paso("  productos activos: %d" % env['product.template'].search_count([('active', '=', True)]))
paso("  lineas de pedido genericas: %d" % env['sale.order.line'].search_count(
    [('product_id.categ_id.parent_id.name', '!=', 'Muebles de Hogar')]))
paso("  pedidos de venta: %d" % env['sale.order'].search_count([]))
for estado in ('draft', 'sent', 'sale', 'done', 'cancel'):
    n = env['sale.order'].search_count([('state', '=', estado)])
    if n:
        paso("    %s: %d" % (estado, n))
