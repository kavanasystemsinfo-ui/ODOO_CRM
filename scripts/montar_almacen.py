# -*- coding: utf-8 -*-
"""
Muebles, fase 2: montar el almacen coherente sobre el catalogo real.

  1. Se asegura la ubicacion virtual de inventario (sin ella Odoo no puede
     mover stock y es lo que dejaba las existencias sin respaldo).
  2. Existencias iniciales de las 80 referencias, con movimiento trazado.
  3. Se confirman los pedidos de compra y se reciben, dejando unos pocos
     pendientes para que se vea mercancia entrando.
  4. Se generan las entregas de los pedidos confirmados y se validan casi
     todas, dejando unas pocas listas para salir.
"""

import random

random.seed(29)

ENTREGAS_EN_CURSO = 4
RECEPCIONES_EN_CURSO = 3


def paso(texto):
    print(texto, flush=True)


def asegurar_ubicacion_ajuste():
    ubicacion = env['stock.location'].with_context(active_test=False).search(
        [('usage', '=', 'inventory')], limit=1)
    if ubicacion:
        return ubicacion
    virtuales = env['stock.location'].with_context(active_test=False).search(
        [('usage', '=', 'view'), ('name', 'ilike', 'virtual')], limit=1)
    if not virtuales:
        virtuales = env['stock.location'].with_context(active_test=False).search(
            [('usage', '=', 'view')], limit=1)
    if not virtuales:
        virtuales = env['stock.location'].create({'name': 'Virtual Locations', 'usage': 'view'})
    ubicacion = env['stock.location'].create({
        'name': 'Inventory adjustment',
        'usage': 'inventory',
        'location_id': virtuales.id,
    })
    datos = env['ir.model.data'].search(
        [('module', '=', 'stock'), ('name', '=', 'stock_location_inventory')], limit=1)
    if datos:
        datos.res_id = ubicacion.id
    else:
        env['ir.model.data'].create({
            'module': 'stock', 'name': 'stock_location_inventory',
            'model': 'stock.location', 'res_id': ubicacion.id, 'noupdate': True,
        })
    return ubicacion


def mover(producto, cantidad, desde, hasta, nombre, origen):
    mov = env['stock.move'].create({
        'name': nombre,
        'product_id': producto.id,
        'product_uom_qty': cantidad,
        'product_uom': producto.uom_id.id,
        'location_id': desde.id,
        'location_dest_id': hasta.id,
        'origin': origen,
    })
    mov._action_confirm()
    mov._action_assign()
    mov.quantity = cantidad
    mov.picked = True
    mov._action_done()


almacen = env['stock.warehouse'].search([], limit=1)
ubicacion_stock = almacen.lot_stock_id
ubicacion_ajuste = asegurar_ubicacion_ajuste()
paso("almacen: %s | stock: %s | ajuste: %s" % (
    almacen.name, ubicacion_stock.complete_name, ubicacion_ajuste.complete_name))

productos = env['product.product'].search([
    ('categ_id.parent_id.name', '=', 'Muebles de Hogar'),
    ('active', '=', True)])
paso("referencias del catalogo: %d" % len(productos))

no_almacenables = [p for p in productos if p.detailed_type != 'product']
for producto in no_almacenables:
    producto.product_tmpl_id.write({'detailed_type': 'product'})
env.cr.commit()
paso("puestas como almacenables: %d" % len(no_almacenables))

# ------------------------------------------------------------------ demanda
demanda = {}
for linea in env['sale.order.line'].search([('order_id.state', '=', 'sale')]):
    demanda[linea.product_id.id] = demanda.get(linea.product_id.id, 0.0) + linea.product_uom_qty
paso("referencias con demanda confirmada: %d" % len(demanda))

# --------------------------------------------------- existencias iniciales
paso("")
paso("=== EXISTENCIAS INICIALES ===")
puestas = 0
unidades = 0.0
for producto in productos:
    objetivo = demanda.get(producto.id, 0.0) + random.randint(10, 40)
    try:
        with env.cr.savepoint():
            mover(producto, objetivo, ubicacion_ajuste, ubicacion_stock,
                  'Inventario inicial', 'Apertura del laboratorio')
            puestas += 1
            unidades += objetivo
    except Exception as exc:
        paso("  aviso %s: %s" % (producto.display_name, str(exc)[:70]))
env.cr.commit()
paso("referencias con existencias iniciales: %d | unidades: %.0f" % (puestas, unidades))

# ------------------------------------------------------ pedidos de compra
paso("")
paso("=== COMPRAS ===")
for pedido in env['purchase.order'].search([('state', '=', 'purchase')]):
    try:
        with env.cr.savepoint():
            pedido.button_cancel()
            pedido.button_draft()
            paso("  %s devuelto a borrador" % pedido.name)
    except Exception as exc:
        paso("  aviso %s: %s" % (pedido.name, str(exc)[:70]))
env.cr.commit()

confirmados = 0
for pedido in env['purchase.order'].search([('state', 'in', ['draft', 'sent'])]):
    try:
        with env.cr.savepoint():
            pedido.button_confirm()
            confirmados += 1
    except Exception as exc:
        paso("  aviso confirmando %s: %s" % (pedido.name, str(exc)[:70]))
env.cr.commit()
paso("pedidos de compra confirmados: %d" % confirmados)

recepciones = env['stock.picking'].search(
    [('picking_type_code', '=', 'incoming'), ('state', 'in', ['confirmed', 'assigned'])], order='id')
paso("recepciones pendientes: %d" % len(recepciones))
a_recibir = recepciones[:max(0, len(recepciones) - RECEPCIONES_EN_CURSO)]
recibidas = 0
for recepcion in a_recibir:
    try:
        with env.cr.savepoint():
            for mov in recepcion.move_ids:
                mov.quantity = mov.product_uom_qty
                mov.picked = True
            recepcion.action_assign()
            recepcion.with_context(skip_sms=True).button_validate()
            recibidas += 1
    except Exception as exc:
        paso("  aviso %s: %s" % (recepcion.name, str(exc)[:70]))
env.cr.commit()
paso("recepciones hechas: %d (quedan pendientes: %d)" % (recibidas, len(recepciones) - recibidas))

# ------------------------------------------------------------- entregas
paso("")
paso("=== ENTREGAS ===")
pedidos = env['sale.order'].search([('state', '=', 'sale')])
paso("pedidos confirmados: %d" % len(pedidos))
lanzados = fallos = 0
for pedido in pedidos:
    if pedido.picking_ids:
        continue
    try:
        with env.cr.savepoint():
            pedido.order_line._action_launch_stock_rule()
            lanzados += 1
    except Exception as exc:
        fallos += 1
        paso("  aviso %s: %s" % (pedido.name, str(exc)[:80]))
env.cr.commit()
paso("entregas lanzadas: %d (avisos: %d)" % (lanzados, fallos))

entregas = env['stock.picking'].search(
    [('picking_type_code', '=', 'outgoing'), ('state', 'in', ['confirmed', 'assigned'])], order='id')
paso("entregas pendientes: %d" % len(entregas))
a_enviar = entregas[:max(0, len(entregas) - ENTREGAS_EN_CURSO)]
enviadas = fallos = 0
for entrega in a_enviar:
    try:
        with env.cr.savepoint():
            entrega.action_assign()
            for mov in entrega.move_ids:
                mov.quantity = mov.product_uom_qty
                mov.picked = True
            entrega.with_context(skip_sms=True).button_validate()
            enviadas += 1
    except Exception as exc:
        fallos += 1
        paso("  aviso %s: %s" % (entrega.name, str(exc)[:80]))
env.cr.commit()
paso("entregas hechas: %d (avisos: %d)" % (enviadas, fallos))

for pendiente in env['stock.picking'].search(
        [('picking_type_code', '=', 'outgoing'), ('state', 'in', ['confirmed', 'assigned'])]):
    try:
        with env.cr.savepoint():
            pendiente.action_assign()
    except Exception:
        pass
env.cr.commit()

# --------------------------------------------------------------- parte
paso("")
paso("=== ALMACEN ===")
for estado in ('draft', 'waiting', 'confirmed', 'assigned', 'done', 'cancel'):
    salida = env['stock.picking'].search_count([('picking_type_code', '=', 'outgoing'), ('state', '=', estado)])
    entrada = env['stock.picking'].search_count([('picking_type_code', '=', 'incoming'), ('state', '=', estado)])
    if salida or entrada:
        paso("  %-10s entregas: %3d | recepciones: %3d" % (estado, salida, entrada))

productos = env['product.product'].search([
    ('categ_id.parent_id.name', '=', 'Muebles de Hogar'), ('active', '=', True)])
con_stock = [p for p in productos if p.qty_available > 0]
paso("referencias con existencias: %d de %d | unidades: %.0f" % (
    len(con_stock), len(productos), sum(p.qty_available for p in productos)))
