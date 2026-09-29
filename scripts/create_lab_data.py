import random

random.seed(42)

# ------------------------------------------------------------
# 1. Company information
# ------------------------------------------------------------
company = env.company
company.write({
    'name': 'Muebles del Hogar S.L.',
    'street': 'Calle Mayor 123',
    'city': 'Castellón',
    'zip': '12001',
    'country_id': env.ref('base.es').id,
    'phone': '+34 964 123 456',
    'email': 'info@mueblesdelhogar.example',
    'website': 'https://mueblesdelhogar.example',
})
print('Company updated:', company.name)

# ------------------------------------------------------------
# 2. Product categories
# ------------------------------------------------------------
parent_categ = env['product.category'].search([('name', '=', 'Muebles de Hogar')], limit=1)
if not parent_categ:
    parent_categ = env['product.category'].create({'name': 'Muebles de Hogar'})

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

categ_ids = {}
for key, name in category_map.items():
    categ = env['product.category'].search([('name', '=', name), ('parent_id', '=', parent_categ.id)], limit=1)
    if not categ:
        categ = env['product.category'].create({'name': name, 'parent_id': parent_categ.id})
    categ_ids[key] = categ.id
print('Categories ready:', len(categ_ids))

# ------------------------------------------------------------
# 3. Standard products from furniture catalog
# ------------------------------------------------------------
furniture_products = env['furniture.product'].search([])
print(f'Furniture products found: {len(furniture_products)}')

created = 0
for fp in furniture_products:
    existing = env['product.template'].search([('name', '=', fp.name)], limit=1)
    if existing:
        continue
    vals = {
        'name': fp.name,
        'list_price': fp.list_price,
        'standard_price': fp.standard_price,
        'categ_id': categ_ids.get(fp.category, parent_categ.id),
        'detailed_type': 'product',
        'sale_ok': True,
        'purchase_ok': True,
        'description_sale': f"{fp.description or ''} | Material: {fp.material or ''} | Dimensiones: {fp.dimensions or ''} | Estilo: {fp.style or ''} | Garantía: {fp.warranty_months or 0} meses".strip(),
        'description': fp.description or '',
    }
    env['product.template'].create(vals)
    created += 1
print(f'Created {created} standard products')

# ------------------------------------------------------------
# 4. Initial stock
# ------------------------------------------------------------
stock_location = env.ref('stock.stock_location_stock', raise_if_not_found=False)
if not stock_location:
    stock_location = env['stock.location'].search([('usage', '=', 'internal')], limit=1)
if stock_location:
    quants_set = 0
    for fp in furniture_products:
        product = env['product.product'].search([('product_tmpl_id.name', '=', fp.name)], limit=1)
        if not product:
            continue
        try:
            existing_quant = env['stock.quant'].search([('product_id', '=', product.id), ('location_id', '=', stock_location.id)], limit=1)
            if existing_quant:
                existing_quant.inventory_quantity = fp.qty_available
                existing_quant.action_apply_inventory()
            else:
                quant = env['stock.quant'].create({
                    'product_id': product.id,
                    'location_id': stock_location.id,
                    'inventory_quantity': fp.qty_available,
                })
                quant.action_apply_inventory()
            quants_set += 1
        except Exception as e:
            print(f'Could not set stock for {fp.name}: {e}')
    print(f'Stock quants set for {quants_set} products')
else:
    print('No internal stock location found; skipping stock setup')

# ------------------------------------------------------------
# 5. Customers
# ------------------------------------------------------------
customer_count = env['res.partner'].search_count([('customer_rank', '>', 0)])
if customer_count < 30:
    to_create = 30 - customer_count
    vals_list = []
    for i in range(to_create):
        vals_list.append({
            'name': f'Cliente Muebles {i+1:02d}',
            'company_type': 'company',
            'customer_rank': 1,
            'email': f'cliente{i+1:02d}@example.com',
            'phone': f'+34 600 {i+1:03d} {i+1:03d}',
            'city': random.choice(['Castellón', 'Valencia', 'Madrid', 'Barcelona', 'Sevilla']),
            'country_id': env.ref('base.es').id,
        })
    env['res.partner'].create(vals_list)
    print(f'Created {to_create} customers')
else:
    print(f'Already {customer_count} customers; skipping creation')

# ------------------------------------------------------------
# 6. Sales orders
# ------------------------------------------------------------
sale_order_count = env['sale.order'].search_count([])
if sale_order_count < 40:
    to_create = 40 - sale_order_count
    customers = env['res.partner'].search([('customer_rank', '>', 0)], limit=50)
    products = env['product.product'].search([('sale_ok', '=', True), ('detailed_type', '=', 'product')], limit=100)
    if customers and products:
        created_orders = 0
        for i in range(to_create):
            partner = random.choice(customers)
            lines = []
            for _ in range(random.randint(1, 5)):
                product = random.choice(products)
                lines.append((0, 0, {
                    'product_id': product.id,
                    'product_uom_qty': random.randint(1, 10),
                    'price_unit': product.list_price,
                }))
            order = env['sale.order'].create({
                'partner_id': partner.id,
                'order_line': lines,
            })
            if i % 2 == 0:
                try:
                    order.action_confirm()
                except Exception as e:
                    print(f'Could not confirm order {order.name}: {e}')
            created_orders += 1
        print(f'Created {created_orders} sales orders')
    else:
        print('No customers or products available for sales orders')
else:
    print(f'Already {sale_order_count} sales orders; skipping creation')

# ------------------------------------------------------------
# 7. Website page
# ------------------------------------------------------------
website = env['website'].search([], limit=1)
if website:
    page = env['website.page'].search([('url', '=', '/muebles')], limit=1)
    if not page:
        page = env['website.page'].create({
            'name': 'Muebles del Hogar',
            'url': '/muebles',
            'website_id': website.id,
            'type': 'qweb',
            'arch': """
                <t t-call="website.layout">
                    <div class="container mt-5">
                        <h1>Muebles del Hogar S.L.</h1>
                        <p class="lead">Empresa ficticia de muebles de hogar con más de 80 productos.</p>
                        <p>Descubre nuestra colección de sofás, mesas, sillas, camas, armarios y mucho más.</p>
                        <a href="/shop" class="btn btn-primary btn-lg">Ver tienda</a>
                    </div>
                </t>
            """,
            'is_published': True,
        })
        print('Created website page /muebles')
    else:
        print('Website page /muebles already exists')
else:
    print('No website found; skipping website page')

env.cr.commit()
print('LAB DATA SETUP COMPLETED')
