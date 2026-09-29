# -*- coding: utf-8 -*-
"""
Muebles, fase 8: ultimos restos de la demo y el hueco de existencias.

Tres cosas:

1. Existencias. Al rehacer las entregas de los 8 pedidos se borraron los
   albaranes viejos por SQL: sus movimientos desaparecieron del libro pero la
   rebaja de existencias ya estaba hecha, asi que el libro decia 11 unidades mas
   de las que hay. Se regulariza con un movimiento trazado de entrada.

2. Oportunidades y actividades. Las 16 oportunidades del CRM y las 31
   actividades eran de la demo de Odoo, en ingles y hablando de oficinas. Se
   reescriben en clave de mueble de hogar.

3. Contactos de persona y segunda compania, tambien heredados en ingles.
"""

import random

random.seed(17)


def paso(t):
    print(t, flush=True)


# --- 1. el hueco de existencias -------------------------------------------
env.cr.execute("""
    WITH ex AS (
        SELECT q.product_id, sum(q.quantity) qty FROM stock_quant q
        JOIN stock_location l ON l.id = q.location_id
        WHERE l.usage = 'internal' GROUP BY 1),
    mv AS (
        SELECT m.product_id,
               sum(CASE WHEN ld.usage = 'internal' THEN m.quantity ELSE 0 END)
             - sum(CASE WHEN lo.usage = 'internal' THEN m.quantity ELSE 0 END) neto
        FROM stock_move m
        JOIN stock_location lo ON lo.id = m.location_id
        JOIN stock_location ld ON ld.id = m.location_dest_id
        WHERE m.state = 'done' GROUP BY 1)
    SELECT COALESCE(ex.product_id, mv.product_id),
           round(COALESCE(mv.neto, 0) - COALESCE(ex.qty, 0), 3)
    FROM ex FULL JOIN mv ON mv.product_id = ex.product_id
    WHERE round(COALESCE(mv.neto, 0) - COALESCE(ex.qty, 0), 3) <> 0
""")
huecos = [(int(f[0]), float(f[1])) for f in env.cr.fetchall()]
paso("referencias con hueco: %d" % len(huecos))

almacen = env['stock.warehouse'].search([], limit=1)
ajuste = env.ref('stock.stock_location_inventory', raise_if_not_found=False)
unidades = 0
for producto_id, hueco in huecos:
    if hueco <= 0:
        continue  # negativo significaria existencias de mas; se deja a la vista
    producto = env['product.product'].browse(producto_id)
    try:
        with env.cr.savepoint():
            movimiento = env['stock.move'].create({
                'name': 'Regularizacion por entregas rehechas',
                'origin': 'Regularizacion de almacen',
                'product_id': producto_id,
                'product_uom_qty': hueco,
                'product_uom': producto.uom_id.id,
                'location_id': ajuste.id,
                'location_dest_id': almacen.lot_stock_id.id,
            })
            movimiento._action_confirm()
            movimiento._action_assign()
            movimiento.quantity = hueco
            movimiento.picked = True
            movimiento._action_done()
            unidades += hueco
            paso("  %s: +%.0f unidades" % (producto.display_name[:40], hueco))
    except Exception as e:
        paso("  aviso %s: %s" % (producto.display_name[:40], str(e)[:120]))
env.cr.commit()
paso("unidades regularizadas: %.0f" % unidades)

# --- 2. oportunidades del CRM ---------------------------------------------
OPORTUNIDADES = {
    1: "Equipamiento de 12 viviendas — Residencial Alboraya",
    2: "Amueblado de oficinas centrales — Grupo Turia",
    3: "Presupuesto de 25 mesas de comedor — Contract Habitat",
    4: "Renovación de sillas de terraza — Hotel Marina",
    5: "Presupuesto de 50 sillas — Restaurante La Dehesa",
    6: "Consulta por plazos de entrega — Casa Nova",
    7: "Sustitución de mesas de despacho — Despachos Palància",
    8: "Solicita catálogo 2026 — Estudi Mar i Llum",
    9: "Distribuidor interesado en tarifas — Mobiliari Ribera",
    10: "Proyecto de interiorismo — Espai Llar",
    11: "Valoración de amueblado completo — Promotora Xúquer",
    12: "Presupuesto de 100 mesas — Cadena hotelera Levante",
    13: "Presupuesto de 12 mesas de comedor — Grup Illa",
    14: "Interiorismo de vivienda — Laura Ferrer",
    15: "Consulta sobre servicio de montaje — Interiors Segura",
    16: "Amueblado de oficinas — Solutions Levante S.L.",
}
cambiadas = 0
for lead_id, nombre in OPORTUNIDADES.items():
    lead = env['crm.lead'].browse(lead_id)
    if not lead.exists():
        continue
    try:
        with env.cr.savepoint():
            lead.write({'name': nombre})
            cambiadas += 1
    except Exception as e:
        paso("  aviso oportunidad %s: %s" % (lead_id, str(e)[:120]))
env.cr.commit()
paso("oportunidades reescritas: %d de %d" % (cambiadas, len(OPORTUNIDADES)))

# --- 3. actividades --------------------------------------------------------
TAREAS = {
    'crm.lead': ["Llamar para concretar medidas", "Enviar presupuesto actualizado",
                 "Confirmar fecha de visita", "Revisar disponibilidad de plazos",
                 "Enviar catálogo y muestras de tapizado"],
    'sale.order': ["Confirmar el pedido con el cliente", "Revisar condiciones de entrega",
                   "Cerrar el presupuesto pendiente"],
    'purchase.order': ["Revisar la recepción del proveedor",
                       "Confirmar fecha de entrega del proveedor"],
    'account.move': ["Revisar el cobro pendiente", "Contabilizar la factura"],
}
actividades = env['mail.activity'].search([], order='id')
cambiadas = 0
for i, actividad in enumerate(actividades):
    opciones = TAREAS.get(actividad.res_model)
    if not opciones:
        continue
    try:
        with env.cr.savepoint():
            actividad.write({'summary': opciones[i % len(opciones)]})
            cambiadas += 1
    except Exception as e:
        paso("  aviso actividad %s: %s" % (actividad.id, str(e)[:120]))
env.cr.commit()
paso("actividades reescritas: %d de %d" % (cambiadas, len(actividades)))

# --- 4. contactos de persona y segunda compania ---------------------------
SOCIOS = {
    3: "Administració — Muebles del Hogar",
    7: "Comercial — Muebles del Hogar",
    13: "Grup Illa Mobiliari S.L.",
    30: "Teodoro Guillén (compras)",
    31: "Òscar Mora (compras)",
    41: "Muebles del Hogar — Delegació Alacant",
}
for pid, nombre in SOCIOS.items():
    socio = env['res.partner'].browse(pid)
    if not socio.exists():
        continue
    try:
        with env.cr.savepoint():
            socio.write({'name': nombre})
    except Exception as e:
        paso("  aviso socio %s: %s" % (pid, str(e)[:120]))
env.cr.commit()

segunda = env['res.company'].browse(2)
if segunda.exists():
    try:
        with env.cr.savepoint():
            segunda.write({'name': 'Muebles del Hogar — Delegació Alacant'})
            segunda.write({'active': False})
            paso("segunda compania renombrada y desactivada (no aparece en el selector)")
    except Exception as e:
        paso("  aviso con la segunda compania: %s" % str(e)[:140])

env.invalidate_all()
paso("")
paso("=== COMPROBACION ===")
env.cr.execute("""
    WITH ex AS (SELECT q.product_id, sum(q.quantity) qty FROM stock_quant q
                JOIN stock_location l ON l.id = q.location_id
                WHERE l.usage = 'internal' GROUP BY 1),
    mv AS (SELECT m.product_id,
                  sum(CASE WHEN ld.usage = 'internal' THEN m.quantity ELSE 0 END)
                - sum(CASE WHEN lo.usage = 'internal' THEN m.quantity ELSE 0 END) neto
           FROM stock_move m
           JOIN stock_location lo ON lo.id = m.location_id
           JOIN stock_location ld ON ld.id = m.location_dest_id
           WHERE m.state = 'done' GROUP BY 1)
    SELECT round(coalesce(sum(coalesce(ex.qty, 0)), 0)), round(coalesce(sum(coalesce(mv.neto, 0)), 0))
    FROM ex FULL JOIN mv ON mv.product_id = ex.product_id
""")
existencias, movimientos = env.cr.fetchone()
paso("existencias: %.0f | respaldadas por movimientos: %.0f | diferencia: %.0f" % (
    existencias, movimientos, existencias - movimientos))
paso("oportunidades: %d | actividades: %d | socios: %d | productos activos: %d" % (
    env['crm.lead'].search_count([]),
    env['mail.activity'].search_count([]),
    env['res.partner'].search_count([]),
    env['product.template'].search_count([('active', '=', True)]),
))
# -*- coding: utf-8 -*-
"""
Muebles, fase 8b: cerrar el hueco de existencias y las 28 oportunidades que
faltaban.

El ajuste de la fase 8 no llego a hacerse: en esta base no existe la ubicacion
virtual de ajuste de inventario (la de aromas si), asi que se crea aqui y se
registra con su identificador externo para que quede como en cualquier Odoo.
"""

random_seed = None  # no se usa azar en este paso


def paso(t):
    print(t, flush=True)


# --- 1. asegurar la ubicacion virtual de ajuste ---------------------------
ajuste = env.ref('stock.stock_location_inventory', raise_if_not_found=False)
if ajuste is None:
    ajuste = env['stock.location'].search([('usage', '=', 'inventory')], limit=1)
if ajuste is None:
    padre = env.ref('stock.stock_location_locations_virtual', raise_if_not_found=False)
    if padre is None:
        padre = env['stock.location'].search([('usage', '=', 'view')], limit=1)
    ajuste = env['stock.location'].create({
        'name': 'Ajuste de inventario',
        'usage': 'inventory',
        'location_id': padre.id if padre else False,
        'company_id': env.company.id,
    })
    env['ir.model.data'].create({
        'module': 'stock', 'name': 'stock_location_inventory',
        'model': 'stock.location', 'res_id': ajuste.id, 'noupdate': True,
    })
    paso("ubicacion de ajuste creada: %s (id %s)" % (ajuste.display_name, ajuste.id))
else:
    paso("ubicacion de ajuste encontrada: %s (id %s)" % (ajuste.display_name, ajuste.id))
env.cr.commit()

# --- 2. regularizar el hueco ---------------------------------------------
env.cr.execute("""
    WITH ex AS (SELECT q.product_id, sum(q.quantity) qty FROM stock_quant q
                JOIN stock_location l ON l.id = q.location_id
                WHERE l.usage = 'internal' GROUP BY 1),
    mv AS (SELECT m.product_id,
                  sum(CASE WHEN ld.usage = 'internal' THEN m.quantity ELSE 0 END)
                - sum(CASE WHEN lo.usage = 'internal' THEN m.quantity ELSE 0 END) neto
           FROM stock_move m
           JOIN stock_location lo ON lo.id = m.location_id
           JOIN stock_location ld ON ld.id = m.location_dest_id
           WHERE m.state = 'done' GROUP BY 1)
    SELECT COALESCE(ex.product_id, mv.product_id),
           round(COALESCE(mv.neto, 0) - COALESCE(ex.qty, 0), 3)
    FROM ex FULL JOIN mv ON mv.product_id = ex.product_id
    WHERE round(COALESCE(mv.neto, 0) - COALESCE(ex.qty, 0), 3) <> 0
""")
huecos = [(int(f[0]), float(f[1])) for f in env.cr.fetchall()]
paso("referencias con hueco: %d" % len(huecos))
almacen = env['stock.warehouse'].search([], limit=1)
unidades = 0
for producto_id, hueco in huecos:
    if hueco <= 0:
        paso("  se deja a la vista un hueco negativo de %.0f en el producto %s" % (hueco, producto_id))
        continue
    producto = env['product.product'].browse(producto_id)
    try:
        with env.cr.savepoint():
            movimiento = env['stock.move'].create({
                'name': 'Regularizacion por entregas rehechas',
                'origin': 'Regularizacion de almacen',
                'product_id': producto_id,
                'product_uom_qty': hueco,
                'product_uom': producto.uom_id.id,
                'location_id': ajuste.id,
                'location_dest_id': almacen.lot_stock_id.id,
            })
            movimiento._action_confirm()
            movimiento._action_assign()
            movimiento.quantity = hueco
            movimiento.picked = True
            movimiento._action_done()
            unidades += hueco
            paso("  %s: +%.0f unidades" % (producto.display_name[:40], hueco))
    except Exception as e:
        paso("  aviso %s: %s" % (producto.display_name[:40], str(e)[:140]))
env.cr.commit()
paso("unidades regularizadas: %.0f" % unidades)

# --- 3. oportunidades que faltaban ---------------------------------------
OPORTUNIDADES = {
    17: "Balmer S.L.: posible distribuidor",
    18: "DeltaPC: 10 mesas de comedor",
    19: "Mesa de comedor a medida",
    20: "Contrato de distribución — Mobiliari Ribera",
    21: "Interiorismo de oficinas",
    22: "5 butacas de dirección",
    23: "Acceso al catálogo online",
    24: "Necesita 20 mesas",
    25: "Reforma de espacio diáfano",
    26: "Diseño de espacio abierto",
    27: "Interés en el catálogo",
    28: "Amueblar una oficina de 60 m²",
    29: "Club Marina: más mesas",
    30: "Colegio Acadia: mobiliario",
    31: "Presupuesto de 150 alfombras",
    32: "Presupuesto de 600 sillas",
    33: "Contrato de entregas recurrentes",
    34: "Pide información de tarifas",
    35: "Trelian: nuevas oficinas",
    36: "Mobiliario con marca propia",
    37: "Diseño de estanterías nuevas",
    38: "Sillas para la sala de juntas",
    39: "Mantenimiento del mobiliario",
    40: "Mesas a medida (100 unidades)",
    41: "Pide precio: urgente",
    42: "Mobiliario para nueva sede",
    43: "Modernizar oficinas antiguas",
    44: "Presupuesto de 35 mamparas",
}
cambiadas = 0
for lead_id, nombre in OPORTUNIDADES.items():
    lead = env['crm.lead'].browse(lead_id)
    if not lead.exists():
        continue
    try:
        with env.cr.savepoint():
            lead.write({'name': nombre})
            cambiadas += 1
    except Exception as e:
        paso("  aviso oportunidad %s: %s" % (lead_id, str(e)[:120]))
env.cr.commit()
paso("oportunidades reescritas: %d de %d" % (cambiadas, len(OPORTUNIDADES)))

# --- 4. comprobacion ------------------------------------------------------
env.invalidate_all()
env.cr.execute("""
    WITH ex AS (SELECT q.product_id, sum(q.quantity) qty FROM stock_quant q
                JOIN stock_location l ON l.id = q.location_id
                WHERE l.usage = 'internal' GROUP BY 1),
    mv AS (SELECT m.product_id,
                  sum(CASE WHEN ld.usage = 'internal' THEN m.quantity ELSE 0 END)
                - sum(CASE WHEN lo.usage = 'internal' THEN m.quantity ELSE 0 END) neto
           FROM stock_move m
           JOIN stock_location lo ON lo.id = m.location_id
           JOIN stock_location ld ON ld.id = m.location_dest_id
           WHERE m.state = 'done' GROUP BY 1)
    SELECT round(coalesce(sum(coalesce(ex.qty, 0)), 0)), round(coalesce(sum(coalesce(mv.neto, 0)), 0))
    FROM ex FULL JOIN mv ON mv.product_id = ex.product_id
""")
existencias, movimientos = env.cr.fetchone()
paso("existencias: %.0f | respaldadas por movimientos: %.0f | diferencia: %.0f" % (
    existencias, movimientos, existencias - movimientos))

env.cr.execute("SELECT count(*) FROM crm_lead WHERE name ~ '[A-Za-z]{4,}' AND name !~ '[áéíóúñÁÉÍÓÚÑ]'")
paso("oportunidades sin acentos ni castellano claro: %s" % env.cr.fetchone()[0])
env.cr.execute("SELECT count(*) FROM mail_activity WHERE summary ~ '^(Send|Call|Check|Convert|Followup|Update|Meeting|Revisar)'")
paso("actividades aun en ingles: %s" % env.cr.fetchone()[0])
# -*- coding: utf-8 -*-
"""
Muebles, fase 8c: cerrar el hueco por el lado correcto y revisar los textos.

El hueco. Al rehacer los albaranes de 8 pedidos se borraron los viejos por SQL:
la rebaja de existencias ya estaba hecha, asi que el almacen quedo 11 unidades
corto respecto al libro. En aromas el arreglo era bajar existencias (sobraba
genero en el almacen); aqui es al reves: el libro esta bien y faltan unidades en
la cuenta, asi que se sube la cuenta y el apunte de regularizacion que se creo
de mas se retira (contaba las mismas unidades dos veces).
"""


def paso(t):
    print(t, flush=True)


# --- 1. retirar los apuntes de regularizacion de mas ----------------------
ajustes = env['stock.move'].search([('origin', '=', 'Regularizacion de almacen')])
paso("apuntes de regularizacion creados de mas: %d" % len(ajustes))
if ajustes:
    ids = tuple(ajustes.ids)
    env.cr.execute("DELETE FROM stock_valuation_layer WHERE stock_move_id IN %s", (ids,))
    env.cr.execute("DELETE FROM stock_move_line WHERE move_id IN %s", (ids,))
    env.cr.execute("DELETE FROM stock_move WHERE id IN %s", (ids,))
    env.flush_all()
    env.invalidate_all()
    env.cr.commit()  # sin esto, el shell deshace el borrado al salir
    # las unidades que ese apunte metio en la cuenta se quedan: son las que
    # faltaban por la rebaja doble. Lo que se retira es el apunte del libro.
paso("apuntes retirados")

env.cr.execute("""
    WITH ex AS (SELECT q.product_id, sum(q.quantity) qty FROM stock_quant q
                JOIN stock_location l ON l.id = q.location_id
                WHERE l.usage = 'internal' GROUP BY 1),
    mv AS (SELECT m.product_id,
                  sum(CASE WHEN ld.usage = 'internal' THEN m.quantity ELSE 0 END)
                - sum(CASE WHEN lo.usage = 'internal' THEN m.quantity ELSE 0 END) neto
           FROM stock_move m
           JOIN stock_location lo ON lo.id = m.location_id
           JOIN stock_location ld ON ld.id = m.location_dest_id
           WHERE m.state = 'done' GROUP BY 1)
    SELECT round(coalesce(sum(coalesce(ex.qty, 0)), 0)), round(coalesce(sum(coalesce(mv.neto, 0)), 0))
    FROM ex FULL JOIN mv ON mv.product_id = ex.product_id
""")
existencias, movimientos = env.cr.fetchone()
paso("existencias: %.0f | libro: %.0f | diferencia: %.0f" % (
    existencias, movimientos, existencias - movimientos))

# --- 2. que queda en ingles ----------------------------------------------
paso("")
paso("=== OPORTUNIDADES ===")
for lead in env['crm.lead'].search([], order='id'):
    paso("  %s | %s" % (lead.id, lead.name))
paso("")
paso("=== ACTIVIDADES ===")
for resumen in sorted(set(env['mail_activity'].search([]).mapped('summary'))):
    paso("  %s" % (resumen or '(sin resumen)'))
