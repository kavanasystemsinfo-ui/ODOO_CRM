# -*- coding: utf-8 -*-
"""
Muebles, fase 7: ultimos socios con nombre heredado de la demo de Odoo.

Quedaban cinco (tres de ellos proveedores de compras reales y el mayor cliente
de la casa) y siete clientes numerados "Cliente Muebles NN". Se renombran al
sector del mueble. Mismo identificador: pedidos, compras y facturas intactos.
Ademas se marca como proveedor a quien tiene pedidos de compra.
"""

def paso(t):
    print(t, flush=True)


RENOMBRES = {
    8: "Estudi Interior Alma S.L.",
    9: "Fusteria Industrial Turia S.L.",
    11: "Mobiliari Alacant Distribucio S.L.",
    12: "Tapisseria i Descans Levante S.L.",
    15: "Fusta i Disseny Segorbe S.L.",
    120: "Habitatges i Moble S.L.",
    121: "Disseny Interior Maestrat S.L.",
    122: "Mobles de Fusta Turia S.L.",
    123: "Estudi Casa i Forma S.L.",
    124: "Interiors Palancia S.L.",
    125: "Mobiliari Urba Valencia S.L.",
    126: "Decoracio i Contract Alacant S.L.",
}

for pid, nombre in RENOMBRES.items():
    socio = env['res.partner'].browse(pid)
    if not socio.exists():
        paso("  aviso: no existe el socio %s" % pid)
        continue
    anterior = socio.name
    try:
        with env.cr.savepoint():
            socio.write({'name': nombre})
            paso("  %s -> %s" % (anterior, nombre))
    except Exception as e:
        paso("  aviso con %s: %s" % (anterior, e))
env.cr.commit()

# quien tenga pedidos de compra es proveedor; quien tenga ventas, cliente
proveedores = env['res.partner'].search([]).filtered(
    lambda s: env['purchase.order'].search_count([('partner_id', '=', s.id)]) > 0)
sin_marca = proveedores.filtered(lambda s: s.supplier_rank == 0)
if sin_marca:
    sin_marca.write({'supplier_rank': 1})
env.cr.commit()

clientes = env['res.partner'].search([]).filtered(
    lambda s: env['sale.order'].search_count([('partner_id', '=', s.id)]) > 0)
sin_marca_cli = clientes.filtered(lambda s: s.customer_rank == 0)
if sin_marca_cli:
    sin_marca_cli.write({'customer_rank': 1})
env.cr.commit()

env.invalidate_all()
paso("proveedores marcados: %d (de %d con compras)" % (len(sin_marca), len(proveedores)))
paso("clientes marcados: %d (de %d con ventas)" % (len(sin_marca_cli), len(clientes)))
paso("socios: %d clientes | %d proveedores" % (
    env['res.partner'].search_count([('customer_rank', '>', 0)]),
    env['res.partner'].search_count([('supplier_rank', '>', 0)]),
))
paso("nombres que quedan de la demo: %s" % (
    env['res.partner'].search([
        '|', ('name', 'ilike', 'Cliente Muebles'),
        '|', ('name', 'ilike', 'Acme'),
        '|', ('name', 'ilike', 'Wood Corner'),
        '|', ('name', 'ilike', 'Gemini Furniture'),
        '|', ('name', 'ilike', 'Ready Mat'),
        '|', ('name', 'ilike', 'Lumber Inc'),
    ]).mapped('name') or 'ninguno'))
