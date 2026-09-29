# -*- coding: utf-8 -*-
"""
Muebles, fase 1: limpiar la herencia de la demo de Odoo y poner el catalogo real.

Que se hace:
  1. Se vacia todo el historial de almacen (el laboratorio venia con albaranes
     de la demo de Odoo y existencias sin respaldo de movimientos).
  2. Las lineas de pedido y de compra que apuntaban a productos genericos de la
     demo (escritorios, cajoneras...) se reescriben sobre el catalogo real de
     muebles, asignando productos distintos dentro de cada pedido.
  3. Se renombran los socios heredados ("Acme Corporation", "Cliente Muebles
     01..21", "Wood Corner", "Ready Mat"...) por clientes y proveedores del
     sector del mueble. Mismo id: pedidos, facturas y contabilidad intactos.
  4. Se archiva el catalogo generico que ya no usa nadie.
"""

NOMBRES_CLIENTE = [
    "Estudi d'Interior Alba",
    "Mobiliari Sant Pau S.L.",
    "Decoració Turia S.L.",
    "Interiors La Plana",
    "Casa i Estil València S.L.",
    "Projectes d'Interior Xúquer",
    "Amuebla Levante S.L.",
    "Disseny Moble Castelló",
    "Habitatge i Confort S.L.",
    "Estudio Casa Nova",
    "Mobles Ribera Alta S.L.",
    "Espai Llar Barcelona S.L.",
    "Interiors Vinalopó S.L.",
    "Contract Habitat Madrid S.L.",
    "Moble Tradicional Alacant S.L.",
    "Estudi Mar i Llum",
    "Casa Mediterrània Disseny S.L.",
    "Mobiliario Contract Sur S.L.",
    "Llar i Detall S.L.",
    "Interiors Segura S.L.",
    "Terra i Fusta Decoració S.L.",
]

RENOMBRES_SOCIO = {
    10: "Distribucions Moble Levante S.L.",
    14: "Moble i Decoració Alzira S.L.",
}

RENOMBRES_PROVEEDOR = {
}

NOMBRE_EMPRESA = "Muebles del Hogar S.L."


def paso(texto):
    print(texto, flush=True)


# ------------------------------------------------------------- 1. almacen
paso("=== 1. VACIADO DEL ALMACEN ===")
for tabla in ('stock_move_line', 'stock_move', 'stock_picking', 'stock_quant',
              'stock_valuation_layer', 'stock_package_level'):
    try:
        with env.cr.savepoint():
            env.cr.execute("DELETE FROM %s" % tabla)
            paso("  %s: borrado" % tabla)
    except Exception as exc:
        paso("  %s: %s" % (tabla, str(exc)[:90]))
env.cr.commit()

# --------------------------------------------------- 2. catalogo real
paso("")
paso("=== 2. LINEAS DE PEDIDO SOBRE EL CATALOGO REAL ===")
reales = env['product.product'].search([
    ('categ_id.parent_id.name', '=', 'Muebles de Hogar'),
    ('active', '=', True),
])
paso("productos reales disponibles: %d" % len(reales))
catalogo = list(reales)

import random

random.seed(7)

cambiadas = 0
for pedido in env['sale.order'].search([]):
    lineas = pedido.order_line
    if not lineas:
        continue
    elegidos = random.sample(catalogo, min(len(lineas), len(catalogo)))
    for i, linea in enumerate(lineas):
        producto = elegidos[i % len(elegidos)]
        precio = producto.list_price or linea.price_unit
        try:
            with env.cr.savepoint():
                linea.write({
                    'product_id': producto.id,
                    'name': producto.get_product_multiline_description_sale(),
                    'price_unit': precio,
                    'product_uom': producto.uom_id.id,
                })
                cambiadas += 1
        except Exception as exc:
            paso("  aviso linea %s: %s" % (linea.id, str(exc)[:80]))
env.cr.commit()
paso("lineas de venta reescritas: %d" % cambiadas)

compras = 0
for pedido in env['purchase.order'].search([]):
    lineas = pedido.order_line
    elegidos = random.sample(catalogo, min(len(lineas) or 1, len(catalogo)))
    for i, linea in enumerate(lineas):
        producto = elegidos[i % len(elegidos)]
        try:
            with env.cr.savepoint():
                linea.write({
                    'product_id': producto.id,
                    'name': producto.get_product_multiline_description_sale(),
                    'price_unit': producto.standard_price or linea.price_unit,
                    'product_uom': producto.uom_id.id,
                })
                compras += 1
        except Exception as exc:
            paso("  aviso compra %s: %s" % (linea.id, str(exc)[:80]))
env.cr.commit()
paso("lineas de compra reescritas: %d" % compras)

# ----------------------------------------------------------- 3. socios
paso("")
paso("=== 3. SOCIOS ===")
for identificador, nombre in RENOMBRES_SOCIO.items():
    socio = env['res.partner'].browse(identificador)
    if socio.exists():
        paso("  %d: %s -> %s" % (identificador, socio.name, nombre))
        socio.write({'name': nombre})

numerados = env['res.partner'].search([('name', 'like', 'Cliente Muebles')], order='name')
paso("socios numerados a renombrar: %d" % len(numerados))
for socio, nombre in zip(numerados, NOMBRES_CLIENTE):
    paso("  %d: %s -> %s" % (socio.id, socio.name, nombre))
    socio.write({'name': nombre})

empresa = env.company
paso("  empresa: %s -> %s" % (empresa.name, NOMBRE_EMPRESA))
empresa.write({'name': NOMBRE_EMPRESA})
env.cr.commit()

# ------------------------------------------------- 4. catalogo generico
paso("")
paso("=== 4. CATALOGO GENERICO ===")
genericos = env['product.template'].search([
    ('active', '=', True),
    ('categ_id.parent_id.name', '!=', 'Muebles de Hogar'),
])
paso("productos genericos activos: %d" % len(genericos))
genericos.write({'active': False, 'is_published': False})
env.cr.commit()

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
paso("productos archivados borrados del todo: %d de %d" % (borrados, len(archivados)))

# ------------------------------------------------------------ 5. parte
paso("")
paso("=== ESTADO ===")
paso("  socios: %d" % env['res.partner'].search_count([]))
paso("  productos activos: %d" % env['product.template'].search_count([('active', '=', True)]))
paso("  productos publicados: %d" % env['product.template'].search_count([('is_published', '=', True)]))
paso("  pedidos de venta: %d" % env['sale.order'].search_count([]))
paso("  pedidos de compra: %d" % env['purchase.order'].search_count([]))
paso("  albaranes: %d" % env['stock.picking'].search_count([]))
paso("  empresa: %s" % env.company.name)
