import json
import random

random.seed(42)

# Load the District Home product data
data_path = '/mnt/extra-addons/ODOO_CRM/data/districthome_products.json'
with open(data_path, encoding='utf-8') as f:
    products = json.load(f)

print(f'Loaded {len(products)} products from District Home data')

# Category mapping
category_map = {
    'sofas': 'Sofás',
    'mesas': 'Mesas',
    'sillas': 'Sillas',
    'camas': 'Camas',
    'armarios': 'Armarios',
    'estanterias': 'Estanterías',
    'escritorios': 'Escritorios',
    'butacas': 'Butacas',
    'mesitas': 'Mesitas',
    'recibidores': 'Recibidores',
    'bancos': 'Bancos',
    'colchones': 'Colchones',
    'otros': 'Otros',
}

# Ensure categories exist
parent_categ = env['product.category'].search([('name', '=', 'Muebles de Hogar')], limit=1)
if not parent_categ:
    parent_categ = env['product.category'].create({'name': 'Muebles de Hogar'})

categ_ids = {}
for key, name in category_map.items():
    categ = env['product.category'].search([('name', '=', name), ('parent_id', '=', parent_categ.id)], limit=1)
    if not categ:
        categ = env['product.category'].create({'name': name, 'parent_id': parent_categ.id})
    categ_ids[key] = categ.id

# Archive existing furniture products
existing = env['product.template'].search([('categ_id.parent_id', '=', parent_categ.id), ('active', '=', True)])
existing.write({'active': False})
print(f'Archived {len(existing)} existing furniture products')

# Create new products
created = 0
for p in products:
    categ_id = categ_ids.get(p.get('category', 'otros'), categ_ids['otros'])
    description = p.get('description', '')
    vendor = p.get('vendor', '')
    if vendor:
        description = f"{description} | Fabricante: {vendor}".strip()
    vals = {
        'name': p.get('title', 'Producto sin nombre'),
        'list_price': p.get('price', 0.0),
        'standard_price': round(p.get('price', 0.0) * 0.6, 2),
        'categ_id': categ_id,
        'detailed_type': 'product',
        'sale_ok': True,
        'purchase_ok': True,
        'description_sale': description,
        'description': description,
        'is_published': True,
        'default_code': p.get('handle', ''),
    }
    env['product.template'].create(vals)
    created += 1

print(f'Created {created} new products from District Home')

# Set initial stock
stock_location = env.ref('stock.stock_location_stock', raise_if_not_found=False)
if not stock_location:
    stock_location = env['stock.location'].search([('usage', '=', 'internal')], limit=1)

quants_set = 0
if stock_location:
    for p in products:
        product = env['product.product'].search([('product_tmpl_id.name', '=', p.get('title'))], limit=1)
        if not product:
            continue
        qty = random.randint(0, 60)
        try:
            existing_quant = env['stock.quant'].search([('product_id', '=', product.id), ('location_id', '=', stock_location.id)], limit=1)
            if existing_quant:
                existing_quant.inventory_quantity = qty
                existing_quant.action_apply_inventory()
            else:
                quant = env['stock.quant'].create({
                    'product_id': product.id,
                    'location_id': stock_location.id,
                    'inventory_quantity': qty,
                })
                quant.action_apply_inventory()
            quants_set += 1
        except Exception as e:
            print(f'Could not set stock for {p.get("title")}: {e}')

print(f'Stock set for {quants_set} products')

env.cr.commit()
print('DISTRICT HOME IMPORT COMPLETED')
