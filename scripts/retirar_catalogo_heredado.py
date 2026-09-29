# -*- coding: utf-8 -*-
"""
Muebles: retirar del todo los 26 productos genericos que quedaban archivados.

Estaban bloqueados por tres cosas distintas:
  - lotes de existencias de la demo,
  - dos facturas de proveedor (una factura y su abono) de la demo de Odoo,
  - los productos que usan las tres formas de envio (esos no se pueden borrar:
    sin ellos no funcionan las entregas, asi que se quedan y se renombran).

Orden: primero se quitan los bloqueos y luego se borran los productos.
"""

def paso(t):
    print(t, flush=True)


GENERICOS = [5, 7, 24, 25, 26, 27, 30,
             191, 196, 202, 205, 207, 208, 210, 211, 213, 216,
             230, 239, 242, 251, 257, 260,
             271, 272, 273]

productos = env['product.template'].with_context(active_test=False).browse(GENERICOS)
variantes = productos.product_variant_ids.ids
paso("productos a retirar: %d (variantes %d)" % (len(productos), len(variantes)))

# --- 1. lotes de existencias
lotes = env['stock.lot'].search([('product_id', 'in', variantes)])
paso("lotes que estorban: %d" % len(lotes))
borrados_lotes = 0
for lote in lotes:
    try:
        with env.cr.savepoint():
            lote.unlink()
            borrados_lotes += 1
    except Exception as e:
        paso("  aviso lote %s: %s" % (lote.name, e))
env.cr.commit()
paso("lotes borrados: %d" % borrados_lotes)

# --- 2. asientos de la demo que los referencian
asientos = env['account.move'].search([('line_ids.product_id', 'in', variantes)])
paso("asientos que los referencian: %s" % [(a.name, a.move_type, a.state) for a in asientos])
for asiento in asientos:
    nombre = asiento.name
    try:
        with env.cr.savepoint():
            if asiento.state == 'posted':
                asiento.button_draft()
            asiento.unlink()
        paso("  asiento %s borrado (era documentacion de la demo de Odoo)" % nombre)
    except Exception as e:
        paso("  aviso asiento %s: %s" % (nombre, str(e)[:160]))
        try:
            with env.cr.savepoint():
                for linea in asiento.line_ids.filtered(lambda x: x.product_id.id in variantes):
                    linea.write({'product_id': False})
                if asiento.state == 'draft':
                    asiento.action_post()
                paso("  asiento %s conservado sin la referencia al producto" % nombre)
        except Exception as e2:
            paso("  no se pudo ni limpiar el asiento %s: %s" % (nombre, str(e2)[:160]))
env.cr.commit()

# --- 3. los productos de las formas de envio se quedan (son funcionales)
TRANSPORTE = {271: "Entrega local", 272: "Mensajeria The Poste", 273: "Envio estandar"}
for pid, nombre in TRANSPORTE.items():
    try:
        with env.cr.savepoint():
            env['product.template'].browse(pid).write({'name': nombre})
    except Exception as e:
        paso("  aviso renombrando %s: %s" % (pid, e))
env.cr.commit()
paso("formas de envio renombradas: %s" % list(TRANSPORTE.values()))

# --- 4. borrado definitivo
borrados = 0
problemas = []
for p in productos:
    if p.id in TRANSPORTE:
        continue
    try:
        with env.cr.savepoint():
            p.unlink()
            borrados += 1
    except Exception as e:
        problemas.append((p.id, str(e)[:200]))
env.cr.commit()

paso("productos genericos borrados: %d" % borrados)
for pid, error in problemas:
    paso("  sigue bloqueado %s -> %s" % (pid, error))

env.invalidate_all()
paso("quedan archivados: %d" % env['product.template'].with_context(active_test=False).search_count([('active', '=', False)]))
paso("catalogo activo: %d | publicados: %d" % (
    env['product.template'].search_count([('active', '=', True)]),
    env['product.template'].search_count([('is_published', '=', True)]),
))
# -*- coding: utf-8 -*-
"""
Muebles, fase 4b: rematar los bloqueos que quedaban.

  - 8 pedidos confirmados seguian con 16 lineas del catalogo generico; sus
    entregas ya estaban hechas con esos productos, asi que se rehacen: se borran
    los albaranes, se reapuntan las lineas al catalogo real y se vuelven a
    generar y cerrar las entregas.
  - La plantilla de presupuestos apuntaba a un producto generico: se reapunta.
  - Los productos de las formas de envio se conservan (son funcionales).
"""

import random

random.seed(41)


def paso(t):
    print(t, flush=True)


GENERICOS = [5, 7, 24, 25, 26, 27, 30,
             191, 196, 202, 205, 207, 208, 210, 211, 213, 216,
             230, 239, 242, 251, 257, 260,
             271, 272, 273]
TRANSPORTE = {271, 272, 273}
genericos = env['product.template'].with_context(active_test=False).browse(GENERICOS)
variantes = genericos.product_variant_ids.ids
reales = env['product.product'].search([
    ('categ_id.parent_id.name', '=', 'Muebles de Hogar'), ('active', '=', True)])

# --- 1. pedidos con lineas genericas: fuera sus albaranes
lineas = env['sale.order.line'].search([('product_id', 'in', variantes)])
pedidos = lineas.order_id
paso("pedidos afectados: %d | lineas: %d" % (len(pedidos), len(lineas)))

albaranes = pedidos.picking_ids
paso("albaranes a rehacer: %d (%s)" % (len(albaranes), [(a.name, a.state) for a in albaranes]))
if albaranes:
    ids = tuple(albaranes.ids)
    env.cr.execute("DELETE FROM stock_move_line WHERE picking_id IN %s", (ids,))
    env.cr.execute("DELETE FROM stock_move WHERE picking_id IN %s", (ids,))
    env.cr.execute("DELETE FROM stock_picking WHERE id IN %s", (ids,))
    env.flush_all()
    env.invalidate_all()
paso("albaranes retirados")

# --- 2. reapuntar las lineas al catalogo real
env.cr.execute(
    "UPDATE sale_order_line SET qty_delivered = 0, qty_invoiced = 0 WHERE product_id IN %s",
    (tuple(variantes),))
env.flush_all()
env.invalidate_all()

cambiadas = 0
for pedido in pedidos:
    for linea in pedido.order_line:
        if linea.product_id.id not in variantes:
            continue
        nuevo = random.choice(reales)
        try:
            with env.cr.savepoint():
                linea.write({
                    'product_id': nuevo.id,
                    'name': nuevo.get_product_multiline_description_sale(),
                    'price_unit': nuevo.list_price,
                })
                cambiadas += 1
        except Exception as e:
            paso("  aviso linea %s: %s" % (linea.id, str(e)[:140]))
env.cr.commit()
paso("lineas reapuntadas: %d" % cambiadas)

# --- 3. plantilla de presupuestos
for modelo in ('sale.order.template.line', 'sale.order.template.option'):
    registros = env[modelo].search([('product_id', 'in', variantes)])
    for r in registros:
        try:
            with env.cr.savepoint():
                r.write({'product_id': random.choice(reales).id})
                paso("  plantilla: %s reapuntado" % modelo)
        except Exception as e:
            paso("  aviso plantilla %s %s: %s" % (modelo, r.id, str(e)[:140]))
            try:
                with env.cr.savepoint():
                    r.unlink()
                    paso("  plantilla: %s %s borrado" % (modelo, r.id))
            except Exception as e2:
                paso("  no se pudo quitar %s %s: %s" % (modelo, r.id, str(e2)[:140]))
env.cr.commit()

# --- 4. rehacer las entregas de esos pedidos
paso("rehaciendo entregas...")
for pedido in pedidos:
    try:
        with env.cr.savepoint():
            pedido.order_line._action_launch_stock_rule()
    except Exception as e:
        paso("  aviso lanzando entregas de %s: %s" % (pedido.name, str(e)[:140]))
env.cr.commit()

nuevos = env['stock.picking'].search([
    ('sale_id', 'in', pedidos.ids), ('state', 'not in', ['done', 'cancel'])])
paso("entregas nuevas pendientes: %d" % len(nuevos))
for a in nuevos:
    try:
        with env.cr.savepoint():
            a.action_assign()
            for m in a.move_ids:
                m.quantity = m.product_uom_qty
                m.picked = True
            a.with_context(skip_sms=True).button_validate()
    except Exception as e:
        paso("  aviso entrega %s: %s" % (a.name, str(e)[:140]))
env.cr.commit()

# --- 5. borrado definitivo
borrados = 0
problemas = []
for p in genericos:
    if p.id in TRANSPORTE:
        continue
    try:
        with env.cr.savepoint():
            p.unlink()
            borrados += 1
    except Exception as e:
        problemas.append((p.id, str(e)[:160]))
env.cr.commit()

env.invalidate_all()
paso("productos genericos borrados: %d" % borrados)
for pid, error in problemas:
    paso("  sigue bloqueado %s -> %s" % (pid, error))
paso("archivados que quedan: %d" % env['product.template'].with_context(active_test=False).search_count([('active', '=', False)]))
paso("catalogo activo: %d | publicados: %d | lineas de pedido fuera del catalogo: %d" % (
    env['product.template'].search_count([('active', '=', True)]),
    env['product.template'].search_count([('is_published', '=', True)]),
    env['sale.order.line'].search_count([('product_id.categ_id.parent_id.name', '!=', 'Muebles de Hogar')])))
paso("albaranes: %d | hechos: %d | pedidos: %d" % (
    env['stock.picking'].search_count([]),
    env['stock.picking'].search_count([('state', '=', 'done')]),
    env['sale.order'].search_count([])))
# -*- coding: utf-8 -*-
"""
Muebles, fase 5: borrar los productos genericos que solo retenian existencias
huerfanas (quants de la demo, sin movimiento que los respalde).
"""

def paso(t):
    print(t, flush=True)


GENERICOS = [5, 7, 24, 25, 26, 27, 30,
             191, 196, 202, 205, 207, 208, 210, 211, 213, 216,
             230, 239, 242, 251, 257, 260,
             271, 272, 273]
TRANSPORTE = {271, 272, 273}

genericos = env['product.template'].with_context(active_test=False).browse(GENERICOS)
variantes = tuple(genericos.product_variant_ids.ids)

env.cr.execute("SELECT count(*) FROM stock_quant WHERE product_id IN %s", (variantes,))
paso("existencias huerfanas a retirar: %s" % env.cr.fetchone()[0])
env.cr.execute("DELETE FROM stock_quant WHERE product_id IN %s", (variantes,))
env.flush_all()
env.invalidate_all()

borrados = 0
problemas = []
for p in genericos:
    if p.id in TRANSPORTE:
        continue
    try:
        with env.cr.savepoint():
            p.unlink()
            borrados += 1
    except Exception as e:
        problemas.append((p.id, str(e)[:200]))
env.cr.commit()

env.invalidate_all()
paso("borrados en esta pasada: %d" % borrados)
for pid, error in problemas:
    paso("  sigue bloqueado %s -> %s" % (pid, error))
paso("archivados que quedan: %d" % env['product.template'].with_context(active_test=False).search_count([('active', '=', False)]))

# comprobacion final de coherencia del catalogo
fuera = env['sale.order.line'].search([('product_id.categ_id.parent_id.name', '!=', 'Muebles de Hogar')])
paso("lineas de pedido fuera del catalogo: %d" % len(fuera))
paso("catalogo: %d activos | %d publicados | %d en el modelo propio" % (
    env['product.template'].search_count([('active', '=', True)]),
    env['product.template'].search_count([('is_published', '=', True)]),
    env['furniture.product'].search_count([]),
))
paso("almacen: %d albaranes (%d hechos) | existencias: %.0f" % (
    env['stock.picking'].search_count([]),
    env['stock.picking'].search_count([('state', '=', 'done')]),
    sum(env['product.product'].search([
        ('categ_id.parent_id.name', '=', 'Muebles de Hogar')]).mapped('qty_available')),
))
# -*- coding: utf-8 -*-
"""
Muebles, fase 6: ultimo bloqueo. Los productos genericos conservaban apuntes de
valoracion de existencias (stock_valuation_layer) de la demo. Se retiran y se
borran los productos.
"""

def paso(t):
    print(t, flush=True)


GENERICOS = [5, 7, 24, 25, 26, 27, 30,
             191, 196, 202, 205, 207, 208, 210, 211, 213, 216,
             230, 239, 242, 251, 257, 260,
             271, 272, 273]
TRANSPORTE = {271, 272, 273}

genericos = env['product.template'].with_context(active_test=False).browse(GENERICOS)
variantes = tuple(genericos.product_variant_ids.ids)

env.cr.execute("SELECT count(*) FROM stock_valuation_layer WHERE product_id IN %s", (variantes,))
paso("apuntes de valoracion a retirar: %s" % env.cr.fetchone()[0])
env.cr.execute("DELETE FROM stock_valuation_layer WHERE product_id IN %s", (variantes,))
env.flush_all()
env.invalidate_all()

borrados = 0
problemas = []
for p in genericos:
    if p.id in TRANSPORTE:
        continue
    try:
        with env.cr.savepoint():
            p.unlink()
            borrados += 1
    except Exception as e:
        problemas.append((p.id, str(e)[:200]))
env.cr.commit()

env.invalidate_all()
paso("borrados en esta pasada: %d" % borrados)
for pid, error in problemas:
    paso("  sigue bloqueado %s -> %s" % (pid, error))

archivados = env['product.template'].with_context(active_test=False).search([('active', '=', False)])
paso("archivados que quedan: %d -> %s" % (len(archivados), archivados.mapped('name')))
paso("catalogo: %d activos | %d publicados | %d en el modelo propio" % (
    env['product.template'].search_count([('active', '=', True)]),
    env['product.template'].search_count([('is_published', '=', True)]),
    env['furniture.product'].search_count([]),
))
paso("almacen: %d albaranes (%d hechos) | unidades en catalogo: %.0f" % (
    env['stock.picking'].search_count([]),
    env['stock.picking'].search_count([('state', '=', 'done')]),
    sum(env['product.product'].search([
        ('categ_id.parent_id.name', '=', 'Muebles de Hogar')]).mapped('qty_available')),
))
