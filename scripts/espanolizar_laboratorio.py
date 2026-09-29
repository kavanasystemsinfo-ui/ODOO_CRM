# -*- coding: utf-8 -*-
"""
Muebles, fase 9a: que el laboratorio sea una empresa espanola, no una demo
americana.

La referencia del catalogo es una tienda de Estados Unidos, pero eso solo
afecto a los datos de origen. Lo que faltaba era la capa de pais:

1. El espanol ni siquiera estaba cargado: solo existia en_US. Se instala y se
   pone por defecto en usuarios, socios y web.
2. La moneda de la empresa era el dolar. Toda cifra con currency_id en dolares
   pasa a euros (los numeros no cambian: son datos de laboratorio).
   El ORM no deja cambiar la moneda de la empresa si hay asientos, asi que se
   hace por SQL y se reinicia Odoo despues para refrescar la cache.
3. Los dos impuestos eran "15%" heredados de la demo. Pasan a IVA 21%.
4. La empresa: pais Espana, provincia de Castellon, direccion y NIF de
   laboratorio.

Se ejecuta con odoo shell y confirma la transaccion al final.
"""

emp = env.company
print("empresa:", emp.name, "| moneda:", emp.currency_id.name)

# --- 1. espanol ---------------------------------------------------------
es = env['res.lang'].with_context(active_test=False).search([('code', '=', 'es_ES')])
if not es:
    print("cargando el idioma es_ES...")
    env['base.language.install'].create({'lang': 'es_ES', 'overwrite': False}).lang_install()
    es = env['res.lang'].with_context(active_test=False).search([('code', '=', 'es_ES')])
es.active = True
print("idioma es_ES activo:", es.active, "|", es.name)

socios = env['res.partner'].with_context(active_test=False).search([])
socios.write({'lang': 'es_ES'})
print("socios en espanol:", len(socios))

webs = env['website'].search([])
if webs:
    webs.write({'default_lang_id': es.id})
    print("web por defecto:", [w.default_lang_id.code for w in webs])

# --- 2. euros ------------------------------------------------------------
eur = env.ref('base.EUR')
usd_id = emp.currency_id.id
eur.active = True

env.cr.execute("""
    SELECT c.table_name FROM information_schema.columns c
    JOIN information_schema.tables t
      ON t.table_name = c.table_name AND t.table_schema = c.table_schema
    WHERE c.column_name = 'currency_id' AND c.table_schema = 'public'
      AND t.table_type = 'BASE TABLE'
      AND c.table_name NOT IN ('account_account', 'res_country', 'res_currency_rate',
                               'payment_currency_rel')
    ORDER BY c.table_name
""")
tablas = [f[0] for f in env.cr.fetchall()]
print("tablas con moneda:", len(tablas))

total = 0
for tabla in tablas:
    env.cr.execute('UPDATE "%s" SET currency_id = %%s WHERE currency_id = %%s' % tabla, (eur.id, usd_id))
    if env.cr.rowcount:
        print("   %-32s %4d filas a euros" % (tabla, env.cr.rowcount))
        total += env.cr.rowcount
print("filas pasadas a euros:", total)

# --- 3. impuestos --------------------------------------------------------
imp_venta = env['account.tax'].with_context(active_test=False).search([('type_tax_use', '=', 'sale')])
imp_compra = env['account.tax'].with_context(active_test=False).search([('type_tax_use', '=', 'purchase')])
imp_venta.write({'name': 'IVA 21%', 'amount': 21.0, 'description': 'IVA 21%'})
imp_compra.write({'name': 'IVA 21% (compras)', 'amount': 21.0, 'description': 'IVA 21%'})
print("impuestos:", [t.name for t in (imp_venta | imp_compra)])

# --- 4. la empresa es espanola ------------------------------------------
pais = env.ref('base.es')
estado = env['res.country.state'].search([('country_id', '=', pais.id), ('name', 'ilike', 'castell')], limit=1)
if not estado:
    estado = env['res.country.state'].search([('country_id', '=', pais.id)], limit=1)
emp.partner_id.write({
    'country_id': pais.id,
    'state_id': estado.id if estado else False,
    'city': 'Castello de la Plana',
    'zip': '12005',
    'street': 'Carrer de la Industria, 24',
    'vat': 'B12345678',
    'website': 'https://muebles.kavanasystems.com',
})
print("empresa:", emp.partner_id.name, "|", emp.partner_id.country_id.name,
      "|", emp.partner_id.state_id.name, "|", emp.partner_id.city, "| NIF", emp.partner_id.vat)

env.flush_all()
env.invalidate_all()
env.cr.commit()
print("CAMBIO CONFIRMADO: idioma, moneda, impuestos y pais de la empresa")
# -*- coding: utf-8 -*-
"""
Muebles, fase 9b: arreglar la web despues de ponerla en espanol.

Que paso. Al fijar la web en espanol (fase 9a) el escaparate empezo a dar 500.
Odoo lo contaba como un fallo de la plantilla website.layout, pero eso era una
mascara: es el fallo conocido de la 17 (odoo/odoo#279928), en el que el
manejador de errores de un bloque t-nocache se rompe y esconde el error real.
El error de verdad estaba debajo:

    File "<960>", line 27, in template_960_t_nocache_0
    IndexError: list index out of range

La plantilla 960 es el selector de idioma. La web tenia como idioma por defecto
es_ES, pero su lista de idiomas habilitados (tabla website_lang_rel) solo tenia
en_US, asi que al buscar el idioma activo en esa lista el indice [0] fallaba.

Arreglo: dejar la lista de idiomas de la web en coherencia con su idioma por
defecto. Empresa espanola: la web queda en espanol.
"""

es = env['res.lang'].with_context(active_test=False).search([('code', '=', 'es_ES')])
en = env['res.lang'].with_context(active_test=False).search([('code', '=', 'en_US')])
print("es_ES activo:", es.active, "| idioma por defecto antes:", [w.default_lang_id.code for w in env['website'].search([])])
print("idiomas de la web antes:", [(w.id, [l.code for l in w.language_ids]) for w in env['website'].search([])])

for web in env['website'].search([]):
    web.write({
        'default_lang_id': es.id,
        'language_ids': [(6, 0, [es.id])],
    })
    print("web %s -> idioma %s | idiomas %s" % (web.id, web.default_lang_id.code, [l.code for l in web.language_ids]))

# El escaparate debe seguir viendo la moneda de la empresa (euros).
emp = env.company
print("empresa %s | moneda %s | pais %s" % (emp.name, emp.currency_id.name, emp.partner_id.country_id.name))
for ordenador in env['product.pricelist'].search([]):
    if ordenador.currency_id != emp.currency_id:
        ordenador.currency_id = emp.currency_id
        print("   tarifa %s pasada a %s" % (ordenador.name, emp.currency_id.name))

env.flush_all()
env.invalidate_all()
env.cr.commit()
print("ARREGLADO Y CONFIRMADO: la web queda en espanol con su lista de idiomas coherente")
# -*- coding: utf-8 -*-
"""
Muebles, fase 9c: el catalogo en espanol.

El origen de los datos es una tienda de Estados Unidos, asi que los 80 muebles
tenian nombre ingles ("Dining Table Eva", "Side Table Thea Tall"...). Se pasan
a espanol conservando el nombre propio del modelo y los codigos de acabado
(CO, CFT, BRZ, SG...), que son referencia interna.

Ademas:
- Las categorias de la tienda eran las de la demo de Odoo (Desks, Furnitures,
  Boxes...). Se sustituyen por el arbol de mueble de hogar en espanol y se
  archiva el heredado.
- Las tarifas ("Christmas", "Benelux", "EUR") pasan a nombres de empresa.
- El dolar se desactiva: la moneda es el euro.

Los nombres se escriben como valor base (idioma en_US) para que el catalogo
tenga un unico nombre, en espanol, en cualquier idioma de la interfaz.
"""

NOMBRES = {
    "Burl Wood Console Susan": "Consola de raíz de nogal Susan",
    "Coffee Table Andrus CFT": "Mesa de centro Andrus CFT",
    "Upholstered Bench Halle": "Banco tapizado Halle",
    "Fluted Cabinet Piper CO": "Armario estriado Piper CO",
    "Coffee Table Keiko CO": "Mesa de centro Keiko CO",
    "Oval Dining Table Jolie CO": "Mesa de comedor ovalada Jolie CO",
    "Oak Chaise Moda": "Chaise longue de roble Moda",
    "Accent Bench Anna": "Banco auxiliar Anna",
    "Mirror Musa S": "Espejo Musa S",
    "Accent Table Iva": "Mesa auxiliar Iva",
    "Side Table Meyer": "Mesita auxiliar Meyer",
    "Dining Table Eva": "Mesa de comedor Eva",
    "Golden Display Unit Kellen": "Vitrina dorada Kellen",
    "Cube Table Vanya": "Mesa cúbica Vanya",
    "Fluted Cabinet Oakley BL": "Armario estriado Oakley BL",
    "Rio Coffee Table": "Mesa de centro Río",
    "Counter Stool Clayton Set of 2": "Taburete de barra Clayton (juego de 2)",
    "Accent Chair Kalani": "Sillón auxiliar Kalani",
    "Nesting Tables Holden": "Mesas nido Holden",
    "Marble Top Coffee Table Hart CT": "Mesa de centro con tablero de mármol Hart CT",
    "Accent Chair Archie BRN": "Sillón auxiliar Archie BRN",
    "Oak Veneer Cabinet Haim": "Armario de chapa de roble Haim",
    "Upholstered Bench Buffy": "Banco tapizado Buffy",
    "Upholstered Curve Dining Chair Joel": "Silla de comedor curva tapizada Joel",
    "Accent Table Norm": "Mesa auxiliar Norm",
    "Keystone Accent Chair": "Sillón auxiliar Keystone",
    "Indigo Velvet Sofa Tristan": "Sofá de terciopelo añil Tristan",
    "Cirrus Sofa": "Sofá Cirrus",
    "Mirror Gabby": "Espejo Gabby",
    "Lounge Chair Irina": "Sillón de descanso Irina",
    "Console Table Amara BRZ": "Mesa consola Amara BRZ",
    "Mirror Naive": "Espejo Naive",
    "Veneer Bedside Table Uma": "Mesita de noche de chapa Uma",
    "Oversized Ottoman Soren OT": "Puf XL Soren OT",
    "Upholstered Bench Keiko": "Banco tapizado Keiko",
    "Black Dots Pouf PoufDot": "Puf de lunares negros PoufDot",
    "Mango Wood Stool Aria": "Taburete de madera de mango Aria",
    "Side Table Mai": "Mesita auxiliar Mai",
    "Outdoor Coffee Table Solaris LW": "Mesa de centro de exterior Solaris LW",
    "Mirror Musa L": "Espejo Musa L",
    "Mirror Dacia": "Espejo Dacia",
    "Side Table Thea Tall": "Mesita auxiliar Thea alta",
    "Outdoor Coffee Table Solaris SW": "Mesa de centro de exterior Solaris SW",
    "Upholstered Curve Counter stool Cybill": "Taburete de barra curvo tapizado Cybill",
    "Marble Side Table Knox": "Mesita auxiliar de mármol Knox",
    "Console Table Vale": "Mesa consola Vale",
    "Fringe Coffee Table Harlan": "Mesa de centro con flecos Harlan",
    "Bench Xavier BN": "Banco Xavier BN",
    "Rectangular Dining Table Hudson SG": "Mesa de comedor rectangular Hudson SG",
    "Coffee Table Danika": "Mesa de centro Danika",
    "Seagrass Upholstered Ottoman Xavier": "Puf tapizado de fibra marina Xavier",
    "Upholstered Counter Stool Brennon": "Taburete de barra tapizado Brennon",
    "Cocktail Table Dina": "Mesa de cóctel Dina",
    "Side Table Set Hade G": "Juego de mesitas auxiliares Hade G",
    "Oak Veneer Dining Table Maria": "Mesa de comedor de chapa de roble María",
    "Accent Table Daxon": "Mesa auxiliar Daxon",
    "Linen Upholstered Stool Avery": "Taburete tapizado de lino Avery",
    "Velvet Left Arm Chaise Tania": "Chaise longue de terciopelo con brazo izquierdo Tania",
    "Upholstered Counter Stool Bala": "Taburete de barra tapizado Bala",
    "Round Side Table Hays CS": "Mesita auxiliar redonda Hays CS",
    "Entry Table Rhea": "Mesa de recibidor Rhea",
    "Sofa Curve": "Sofá Curve",
    "Bar Stool Clayton Set of 2": "Taburete de barra Clayton (juego de 2) B",
    "Marble Top Coffee Table London": "Mesa de centro con tablero de mármol London",
    "Outdoor Coffee Table Solaris SB": "Mesa de centro de exterior Solaris SB",
    "Upholstered Stool Fiona BW": "Taburete tapizado Fiona BW",
    "Cabinet Joan NAT": "Armario Joan NAT",
    "Wine Cabinet Heidi CH": "Vinoteca Heidi CH",
    "Wine Cabinet Hamish": "Vinoteca Hamish",
    "Small Coffee Table Veda": "Mesa de centro pequeña Veda",
    "Console Table Umber": "Mesa consola Umber",
    "Marble Top Coffee Table Quest": "Mesa de centro con tablero de mármol Quest",
    "Small Sofa Teegan": "Sofá pequeño Teegan",
    "Mirror Geneva S": "Espejo Geneva S",
    "Round Side Table Hays NVYS": "Mesita auxiliar redonda Hays NVYS",
    "Tufted Gallery Bench Werner BRZ": "Banco capitoné Werner BRZ",
    "Wine Cabinet Bliss": "Vinoteca Bliss",
    "Armchair Rico": "Sillón Rico",
    "Cocktail Table Kai": "Mesa de cóctel Kai",
    "Cabinet Joan BRN": "Armario Joan BRN",
}

CATEGORIAS = {
    'sofas': 'Sofás y chaise longue',
    'mesas': 'Mesas de comedor',
    'mesitas': 'Mesitas y mesas de centro',
    'sillas': 'Sillas y taburetes',
    'butacas': 'Sillones y butacas',
    'bancos': 'Bancos y pufs',
    'armarios': 'Armarios y vitrinas',
    'estanterias': 'Estanterías y librerías',
    'escritorios': 'Despacho',
    'camas': 'Dormitorio',
    'recibidores': 'Recibidores y consolas',
    'colchones': 'Colchones',
    'otros': 'Decoración y espejos',
}

raiz = env['product.public.category'].with_context(active_test=False).search([('name', '=', 'Muebles de hogar')], limit=1)
if not raiz:
    raiz = env['product.public.category'].with_context(active_test=False).create({'name': 'Muebles de hogar'})
print("categoria raiz:", raiz.id, raiz.name)

destino = {}
for clave, nombre in CATEGORIAS.items():
    cat = env['product.public.category'].with_context(active_test=False).search(
        [('name', '=', nombre), ('parent_id', '=', raiz.id)], limit=1)
    if not cat:
        cat = env['product.public.category'].with_context(active_test=False).create(
            {'name': nombre, 'parent_id': raiz.id})
    # el modelo de categorias de tienda no tiene campo de archivado: si ya
    # existe se reutiliza tal cual
    destino[clave] = cat

renombrados = 0
sin_categoria = []
for viejo, nuevo in NOMBRES.items():
    pt = env['product.template'].with_context(active_test=False).search([('name', '=', viejo)], limit=1)
    if not pt:
        print("  OJO, no encontrado:", viejo)
        continue
    pt.with_context(lang='en_US').write({'name': nuevo})
    renombrados += 1

    ficha = env['furniture.product'].with_context(active_test=False).search([('name', '=', viejo)], limit=1)
    if ficha:
        ficha.write({'name': nuevo})
        cat = destino.get(ficha.category)
        if cat:
            pt.public_categ_ids = [(6, 0, [cat.id])]
        else:
            sin_categoria.append(nuevo)
    else:
        sin_categoria.append(nuevo)
print("productos renombrados:", renombrados, "| sin categoria asignada:", len(sin_categoria))
for nombre in sin_categoria[:10]:
    print("   sin categoria:", nombre)

# las categorias heredadas de la demo: el modelo no admite archivarlas, asi que
# se quitan de los productos que aun las usen y se borran de hoja a raiz
heredadas = ['Desks', 'Furnitures', 'Boxes', 'Drawers', 'Cabinets', 'Bins', 'Lamps',
             'Services', 'Multimedia', 'Components', 'Chairs', 'Couches']
demo = env['product.public.category'].with_context(active_test=False).search([('name', 'in', heredadas)])
resto = env['product.template'].with_context(active_test=False).search([('public_categ_ids', 'in', demo.ids)])
if resto:
    resto.write({'public_categ_ids': [(5, 0)]})
print("categorias de la demo:", len(demo), "| productos desvinculados de ellas:", len(resto))
for cat in demo.sorted(lambda c: -c.id):
    cat.unlink()
print("categorias de la demo borradas")

# tarifas
tarifas = {'Christmas': 'Tarifa de temporada', 'Benelux': 'Tarifa distribuidores', 'EUR': 'Tarifa pública'}
for viejo, nuevo in tarifas.items():
    tar = env['product.pricelist'].search([('name', '=', viejo)], limit=1)
    if tar:
        tar.write({'name': nuevo})
        print("tarifa %s -> %s (%s)" % (viejo, nuevo, tar.currency_id.name))

# el dolar fuera
usd = env.ref('base.USD')
usd.active = False
print("dolar activo:", usd.active, "| euro activo:", env.ref('base.EUR').active)

env.flush_all()
env.invalidate_all()
env.cr.commit()
print("CONFIRMADO: catalogo, categorias y tarifas en espanol; moneda unica el euro")
# -*- coding: utf-8 -*-
"""Muebles, fase 9c-bis: el ultimo nombre en ingles que quedo.

El catalogo traia "Tufted Gallery Bench Werner BR" (el codigo es BR, no BRZ),
que no coincidia con la lista. Se renombra a mano en los dos sitios: el
producto y la ficha del modelo propio.
"""
VIEJO = "Tufted Gallery Bench Werner BR"
NUEVO = "Banco capitoné Werner BR"

pt = env['product.template'].with_context(active_test=False).search([('name', '=', VIEJO)], limit=1)
if pt:
    pt.with_context(lang='en_US').write({'name': NUEVO})
    print("producto %s -> %s" % (pt.id, NUEVO))
else:
    print("no encontrado el producto:", VIEJO)

ficha = env['furniture.product'].with_context(active_test=False).search([('name', '=', VIEJO)], limit=1)
if ficha:
    ficha.write({'name': NUEVO})
    print("ficha del modelo %s -> %s" % (ficha.id, NUEVO))

env.cr.commit()

# recuento final: ningun nombre del catalogo con palabras inglesas de mueble
inglesas = ['Table', 'Sofa', 'Chair', 'Cabinet', 'Bench', 'Mirror', 'Console', 'Stool',
            'Chaise', 'Ottoman', 'Pouf', 'Cocktail', 'Armchair', 'Nesting', 'Upholstered',
            'Veneer', 'Seagrass', 'Golden', 'Oversized', 'Indigo', 'Mango', 'Black Dots',
            'Display Unit', 'Cube Table', 'Burl', 'Fringe', 'Buffy', 'Keystone']
malos = []
for p in env['product.template'].with_context(active_test=False).search([('active', '=', True)]):
    nombre = p.with_context(lang='en_US').name
    if any(palabra in nombre for palabra in inglesas):
        malos.append(nombre)
print("productos activos:", env['product.template'].search_count([('active', '=', True)]))
print("nombres todavia en ingles:", len(malos), malos[:5])
# -*- coding: utf-8 -*-
"""
Muebles, fase 9d: cargar de verdad las traducciones del espanol.

Que paso. En la fase 9a el idioma es_ES ya existia como ficha inactiva en la
base (Odoo trae las 91 lenguas creadas), asi que el bloque que instala las
traducciones se salto: solo se puso activo. Resultado: interfaz en ingles
("Search", "Sort By", "Add to Cart") con precios en euros.

Aqui se importan los ficheros de traduccion de los modulos instalados para
es_ES. Es una operacion pesada (miles de terminos), asi que se confirma al
final y se avisa del recuento.
"""

env.cr.execute("SELECT count(*) FROM ir_ui_view WHERE arch_db ? 'es_ES'")
antes = env.cr.fetchone()[0]
print("vistas con traduccion es_ES antes:", antes)

wizard = env['base.language.install'].create({
    'lang_ids': [(6, 0, [env['res.lang'].with_context(active_test=False).search([('code', '=', 'es_ES')]).id])],
    'overwrite': True,
})
print("cargando traducciones de es_ES...")
wizard.lang_install()
env.flush_all()
env.cr.commit()

env.cr.execute("SELECT count(*) FROM ir_ui_view WHERE arch_db ? 'es_ES'")
despues = env.cr.fetchone()[0]
print("vistas con traduccion es_ES despues:", despues)

env.cr.execute("""
    SELECT count(*) FROM ir_ui_view
    WHERE arch_db->>'es_ES' LIKE '%Añadir al carrito%'
       OR arch_db->>'es_ES' LIKE '%Buscar%'
""")
print("vistas con textos de tienda en espanol:", env.cr.fetchone()[0])

lang = env['res.lang'].with_context(active_test=False).search([('code', '=', 'es_ES')])
print("idioma:", lang.code, "| activo:", lang.active)
env.cr.commit()
print("CONFIRMADO: traducciones del espanol cargadas")
# -*- coding: utf-8 -*-
"""
Muebles, fase 9e: los documentos con el IVA espanol.

Los dos impuestos se renombraron a IVA 21% en la fase 9a, pero los importes ya
calculados siguen al 15% de la demo: cambiar el tipo de un impuesto no rehace lo
que ya esta calculado. Aqui se reescribe el impuesto de las lineas para que Odoo
vuelva a calcular.

Notas de la version 17, que me costo un intento: en las lineas de pedido el
campo es tax_id (singular) en venta y taxes_id en compra, no tax_ids.

Las dos facturas de proveedor contabilizadas se reabren, se les pone el IVA
nuevo y se vuelven a contabilizar. El resto de asientos son de banco y varios,
sin IVA, y se quedan como estan.
"""


def campo_impuesto(modelo):
    for nombre in ('tax_id', 'tax_ids', 'taxes_id'):
        if nombre in env[modelo]._fields:
            return nombre
    raise ValueError("no encuentro el campo de impuestos en " + modelo)


campo_venta = campo_impuesto('sale.order.line')
campo_compra = campo_impuesto('purchase.order.line')
print("campo de impuestos en venta:", campo_venta, "| en compra:", campo_compra)

venta = env['account.tax'].with_context(active_test=False).search([('type_tax_use', '=', 'sale')], limit=1)
compra = env['account.tax'].with_context(active_test=False).search([('type_tax_use', '=', 'purchase')], limit=1)
print("IVA de venta:", venta.name, venta.amount, "| IVA de compra:", compra.name, compra.amount)

print("\n--- pedidos de venta ---")
tocados, sin_tocar = 0, []
for orden in env['sale.order'].search([], order='id'):
    if orden.state in ('done', 'cancel'):
        sin_tocar.append((orden.name, orden.state))
        continue
    try:
        orden.order_line.write({campo_venta: [(6, 0, [venta.id])]})
        tocados += 1
    except Exception as error:
        sin_tocar.append((orden.name, str(error)[:70]))
print("pedidos de venta con el IVA actualizado:", tocados, "| sin tocar:", len(sin_tocar))
for nombre, motivo in sin_tocar[:5]:
    print("   ", nombre, "->", motivo)

print("\n--- pedidos de compra ---")
tocados_c = 0
for orden in env['purchase.order'].search([], order='id'):
    if orden.state in ('done', 'cancel'):
        continue
    try:
        orden.order_line.write({campo_compra: [(6, 0, [compra.id])]})
        tocados_c += 1
    except Exception as error:
        print("   sin tocar", orden.name, str(error)[:70])
print("pedidos de compra con el IVA actualizado:", tocados_c)

print("\n--- facturas de proveedor contabilizadas ---")
for factura in env['account.move'].search([('move_type', 'in', ('in_invoice', 'in_refund')),
                                           ('state', '=', 'posted')], order='id'):
    antes = factura.amount_tax
    factura.button_draft()
    factura.invoice_line_ids.write({'tax_ids': [(6, 0, [compra.id])]})
    factura.action_post()
    print("   %-18s IVA %.2f -> %.2f | total %.2f" % (factura.name, antes, factura.amount_tax, factura.amount_total))

print("\n--- comprobacion ---")
for orden in env['sale.order'].search([('state', '=', 'sale')], limit=3, order='id'):
    porcentaje = (orden.amount_tax / orden.amount_untaxed * 100) if orden.amount_untaxed else 0
    print("  %s base %.2f + IVA %.2f = %.2f (%.1f%%)" % (orden.name, orden.amount_untaxed,
                                                        orden.amount_tax, orden.amount_total, porcentaje))

env.flush_all()
env.invalidate_all()
env.cr.commit()
env.registry.signal_changes()
env.cr.commit()
print("CONFIRMADO: pedidos y facturas con el IVA espanol")
# -*- coding: utf-8 -*-
"""
Muebles, fase 9f: retirar las ultimas facturas de la demo.

Quedaban tres asientos de factura heredados de la demo de Odoo: una factura de
proveedor, su abono y una factura vacia en borrador. Su linea dice "Redeem
Reference Number: PO02529", una referencia que no existe en este catalogo, y sus
apuntes de impuesto seguian con el 15% de la demo (el tipo ya es IVA 21%).

Es el mismo criterio que se aplico en la fase 6 con las facturas de productos
inexistentes: no dejar documentado lo que no existe. Los otros once asientos son
de banco y varios, sin IVA, y se quedan.

Se cierran tambien las comprobaciones: ningun documento con impuesto distinto del
IVA espanol.
"""

movimientos = env['account.move'].search([('move_type', 'in', ('in_invoice', 'in_refund', 'out_invoice', 'out_refund'))], order='id')
print("asientos de factura que hay:", len(movimientos))
for m in movimientos:
    print("   %-18s %-10s %-8s total %10.2f IVA %8.2f" % (m.name, m.move_type, m.state, m.amount_total, m.amount_tax))

retirados = 0
for m in movimientos:
    try:
        if m.state != 'draft':
            m.button_draft()
        nombre = m.name
        m.unlink()
        retirados += 1
        print("   retirado:", nombre)
    except Exception as error:
        print("   NO se pudo retirar", m.name, "->", str(error)[:90])

print("asientos de factura retirados:", retirados)
print("asientos que quedan:", env['account.move'].search_count([]))

print("\n--- comprobacion de impuestos en todo lo que queda ---")
impuestos_usados = set()
for linea in env['account.move.line'].search([('tax_ids', '!=', False)]):
    for t in linea.tax_ids:
        impuestos_usados.add((t.name, t.amount))
print("impuestos presentes en el libro:", impuestos_usados)
print("productos con el IVA de venta:", env['product.template'].search_count([('taxes_id', 'in', env['account.tax'].search([('type_tax_use', '=', 'sale')]).ids)]))

for orden in env['sale.order'].search([('state', 'in', ('sale', 'draft'))], limit=2, order='id'):
    porcentaje = (orden.amount_tax / orden.amount_untaxed * 100) if orden.amount_untaxed else 0
    print("  ejemplo de pedido: %s base %.2f + IVA %.2f = %.2f (%.1f%%)" % (orden.name, orden.amount_untaxed,
                                                                          orden.amount_tax, orden.amount_total, porcentaje))

env.flush_all()
env.invalidate_all()
env.cr.commit()
env.registry.signal_changes()
env.cr.commit()
print("CONFIRMADO: el libro queda sin documentos de la demo")
# -*- coding: utf-8 -*-
"""
Muebles, fase 9g: colocar cada mueble en su categoria de tienda.

La clasificacion que venia del modelo propio metia 34 productos en "Mesas de
comedor" (incluidas mesas de centro). Ahora que los nombres estan en espanol, se
clasifica por el nombre, que es lo que ve el cliente en el escaparate.

De paso se comprueba que las 12 categorias de la tienda queden coherentes.
"""

DESTINO = {
    'mesitas': 'Mesitas y mesas de centro',
    'mesas': 'Mesas de comedor',
    'recibidores': 'Recibidores y consolas',
    'sofas': 'Sofás y chaise longue',
    'butacas': 'Sillones y butacas',
    'sillas': 'Sillas y taburetes',
    'bancos': 'Bancos y pufs',
    'armarios': 'Armarios y vitrinas',
    'otros': 'Decoración y espejos',
}

# el orden importa: lo mas especifico primero
REGLAS = [
    ('mesa de centro', 'mesitas'),
    ('mesa de cóctel', 'mesitas'),
    ('mesa cubica', 'mesitas'),
    ('mesa cúbica', 'mesitas'),
    ('mesas nido', 'mesitas'),
    ('mesita', 'mesitas'),
    ('mesa auxiliar', 'mesitas'),
    ('juego de mesitas', 'mesitas'),
    ('mesa de comedor', 'mesas'),
    ('consola', 'recibidores'),
    ('recibidor', 'recibidores'),
    ('sofá', 'sofas'),
    ('sofa', 'sofas'),
    ('chaise', 'sofas'),
    ('sillón', 'butacas'),
    ('sillon', 'butacas'),
    ('silla', 'sillas'),
    ('taburete', 'sillas'),
    ('banco', 'bancos'),
    ('puf', 'bancos'),
    ('vinoteca', 'armarios'),
    ('vitrina', 'armarios'),
    ('armario', 'armarios'),
    ('espejo', 'otros'),
]

categorias = {}
for clave, nombre in DESTINO.items():
    cat = env['product.public.category'].search([('name', '=', nombre)], limit=1)
    if not cat:
        print("OJO, falta la categoria:", nombre)
        continue
    categorias[clave] = cat

raiz = env['product.public.category'].search([('name', '=', 'Muebles de hogar')], limit=1)

reparto = {}
sin_sitio = []
for producto in env['product.template'].search([('active', '=', True)], order='id'):
    nombre = producto.with_context(lang='en_US').name
    clave = 'otros'
    for palabra, destino in REGLAS:
        if palabra in nombre.lower():
            clave = destino
            break
    cat = categorias.get(clave)
    if not cat:
        sin_sitio.append(nombre)
        continue
    if producto.public_categ_ids != cat:
        producto.public_categ_ids = [(6, 0, [cat.id])]
    reparto[cat.name] = reparto.get(cat.name, 0) + 1

print("reparto de los 80 muebles:")
for nombre, cuantos in sorted(reparto.items(), key=lambda x: -x[1]):
    print("   %-28s %3d" % (nombre, cuantos))
print("total clasificado:", sum(reparto.values()), "| sin sitio:", len(sin_sitio))

# las tres categorias que se pensaron y no tienen muebles: se dejan vacias y se
# avisa, para no ensenar un escaparate con secciones huerfanas
vacias = [c.name for clave, c in categorias.items()
          if c.name not in reparto]
print("categorias sin muebles (no se ensenan si estan vacias):", vacias)

env.flush_all()
env.invalidate_all()
env.cr.commit()
env.registry.signal_changes()
env.cr.commit()
print("CONFIRMADO: cada mueble en su categoria de tienda")
# -*- coding: utf-8 -*-
"""
Muebles, fase 9h: cerrar el arbol de la tienda.

Dos remates:
- La mesita de noche estaba en "Mesitas": su sitio es "Dormitorio".
- Quedaban categorias pensadas sin ningun mueble (Despacho, Estanterias,
  Colchones). Un menu con secciones vacias no ayuda a nadie: se borran. Si
  algun dia entran muebles de esos tipos, se vuelven a crear.
"""

dormitorio = env['product.public.category'].search([('name', '=', 'Dormitorio')], limit=1)
if dormitorio:
    for producto in env['product.template'].search([('active', '=', True)]):
        nombre = producto.with_context(lang='en_US').name.lower()
        if 'mesita de noche' in nombre:
            producto.public_categ_ids = [(6, 0, [dormitorio.id])]
            print("a Dormitorio:", producto.with_context(lang='en_US').name)

for nombre in ('Despacho', 'Estanterías y librerías', 'Colchones'):
    cat = env['product.public.category'].search([('name', '=', nombre)], limit=1)
    if cat and not env['product.template'].search_count([('public_categ_ids', 'in', cat.ids)]):
        cat.unlink()
        print("categoria vacia borrada:", nombre)

env.flush_all()
env.invalidate_all()
env.cr.commit()
env.registry.signal_changes()
env.cr.commit()

print("\n--- el arbol de la tienda queda asi ---")
raiz = env['product.public.category'].search([('name', '=', 'Muebles de hogar')], limit=1)
for cat in env['product.public.category'].search([], order='id'):
    cuantos = env['product.template'].search_count([('public_categ_ids', 'in', cat.ids)])
    padre = cat.parent_id.name or '-'
    print("   %-28s padre: %-18s muebles: %3d" % (cat.name, padre, cuantos))
print("categorias en total:", env['product.public.category'].search_count([]))
