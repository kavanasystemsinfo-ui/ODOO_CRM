# -*- coding: utf-8 -*-
"""Arreglos de datos de la demo (2026-11-07). Se ejecuta con `odoo shell`.

Fallos que la demo arrastraba desde la v1 y que encontró la prueba a fondo
tras el despliegue de la v2 (no los causó el despliegue: la copia v1 tenía
exactamente lo mismo):

1. Moneda. La compañía trabaja en EUR pero EUR estaba DESACTIVADO y USD
   activo (al revés de lo que pretendía espanolizar_laboratorio.py), así que
   no se podía publicar ninguna factura. Además 50 pedidos y las 10 facturas
   se crearon en USD. No hay tipos de cambio (1:1) y todos los apuntes en USD
   tienen importe en divisa = importe contable, así que pasarlos a EUR no
   cambia ningún importe. Se activa EUR, se pasan esos documentos a EUR y se
   desactiva USD. res_country no se toca (EE. UU. sigue con su dólar).
2. Secuencias. Los contadores de pedidos de venta (S), compras (P),
   recepciones (WH/IN/) y entregas (WH/OUT/) iban por detrás de los nombres
   que ya existían: confirmar una compra chocaba con WH/IN/00012.
3. El usuario de visita no tenía ninguna compañía permitida: no podía crear
   oportunidades ("company crossover").
4. Ficheros perdidos del filestore (iconos de las aplicaciones, logo, favicon,
   tableros...). Los que vienen de un módulo se recargan del fichero original
   del módulo; el logo, de demo/video/logo_mh.png; lo que no tiene origen
   recuperable se suelta (el campo queda vacío y Odoo pinta su imagen por
   defecto en vez de dar error).

Idempotente: ejecutarlo dos veces no cambia nada la segunda.
Imprime ARREGLOS_OK al final si todo cuadra.
"""
import base64
import os
import re
from pathlib import Path

from lxml import etree
from odoo.modules.module import get_manifest
from odoo.tools import file_open
from odoo.tools.binary import BinaryBytes

informe = []


def nota(texto):
    informe.append(texto)
    print(texto)


# ---------------------------------------------------------------- 1. moneda
eur = env.ref('base.EUR')
usd = env.ref('base.USD')
if not eur.active:
    eur.active = True
    nota('moneda: EUR activado')
env.cr.execute("SELECT count(*) FROM res_currency_rate WHERE currency_id IN %s", ((eur.id, usd.id),))
tipos = env.cr.fetchone()[0]
env.cr.execute("SELECT count(*) FROM account_move_line WHERE currency_id = %s "
               "AND round(amount_currency, 2) <> round(balance, 2)", (usd.id,))
distintos = env.cr.fetchone()[0]
if tipos or distintos:
    nota(f'moneda: NO se convierten documentos USD (tipos de cambio={tipos}, apuntes con importe distinto={distintos})')
else:
    for tabla in ('sale_order', 'sale_order_line', 'account_move', 'account_move_line'):
        env.cr.execute(f'UPDATE {tabla} SET currency_id = %s WHERE currency_id = %s', (eur.id, usd.id))
        if env.cr.rowcount:
            nota(f'moneda: {tabla} {env.cr.rowcount} filas USD -> EUR')
    env.invalidate_all()
env.cr.execute("SELECT count(*) FROM product_pricelist WHERE currency_id = %s AND active", (usd.id,))
tarifas_usd = env.cr.fetchone()[0]  # leer antes de tocar el ORM: otra consulta pisaría el resultado
if usd.active and not tarifas_usd:
    usd.active = False
    nota('moneda: USD desactivado')

# ---------------------------------------------------------------- 2. secuencias
tablas = {'stock_picking': 'name', 'sale_order': 'name', 'purchase_order': 'name'}
for seq in env['ir.sequence'].search([('prefix', '!=', False)]):
    if '%(' in (seq.prefix or '') or '%(' in (seq.suffix or ''):
        continue
    mayor = 0
    patron = re.compile(re.escape(seq.prefix) + r'(\d+)' + re.escape(seq.suffix or '') + '$')
    for tabla, campo in tablas.items():
        env.cr.execute(f'SELECT {campo} FROM {tabla} WHERE {campo} LIKE %s', (seq.prefix + '%',))
        for (nombre,) in env.cr.fetchall():
            m = patron.match(nombre or '')
            if m:
                mayor = max(mayor, int(m.group(1)))
    if mayor and seq.number_next_actual <= mayor:
        antes = seq.number_next_actual
        seq.number_next = mayor + 1
        nota(f'secuencia {seq.prefix}: siguiente {antes} -> {mayor + 1} (ya existía hasta {mayor})')

# ---------------------------------------------------------------- 3. compañías
compania = env.ref('base.main_company')
sin = env['res.users'].search([('share', '=', False)]).filtered(lambda u: not u.company_ids)
for usuario in sin:
    usuario.write({'company_ids': [(4, compania.id)], 'company_id': compania.id})
    nota(f'usuario {usuario.login}: compañía permitida {compania.name}')

# ---------------------------------------------------------------- 5. stock
# Ningún mueble era almacenable (se perdió al migrar de Odoo 17 a 20, donde el
# viejo "producto almacenable" pasó a ser tipo 'consu' + is_storable): las
# entregas y recepciones no movían las existencias.
no_almacenables = env['product.template'].search([('is_furniture', '=', True), ('is_storable', '=', False)])
if no_almacenables:
    no_almacenables.write({'is_storable': True})
    nota(f'stock: {len(no_almacenables)} muebles marcados como almacenables')
# Al hacerlo, Odoo reconstruye quants desde el historial; los sembrados en su
# día no tenían compañía y por eso no se fusionaban (quedaban parejas +/-).
env.cr.execute("""UPDATE stock_quant q SET company_id = l.company_id FROM stock_location l
                   WHERE l.id = q.location_id AND q.company_id IS NULL AND l.company_id IS NOT NULL""")
if env.cr.rowcount:
    nota(f'stock: {env.cr.rowcount} quants sin compañía corregidos')
env.invalidate_all()
env['stock.quant'].sudo()._quant_tasks()
env.flush_all()

# ---------------------------------------------------------------- 4. ficheros perdidos
Adjunto = env['ir.attachment'].sudo()


def falta(adj):
    return adj.store_fname and not os.path.exists(adj._full_path(adj.store_fname))


def perdidos():
    env.cr.execute("SELECT id FROM ir_attachment WHERE store_fname IS NOT NULL")
    return Adjunto.browse([r[0] for r in env.cr.fetchall()]).filtered(falta)


# 4a. iconos de menú: reescribir web_icon recalcula web_icon_data desde el módulo
menus = env['ir.ui.menu'].with_context(active_test=False).browse(
    perdidos().filtered(lambda a: a.res_model == 'ir.ui.menu' and a.res_field == 'web_icon_data').mapped('res_id'))
for menu in menus:
    menu.write({'web_icon': menu.web_icon})
if menus:
    nota(f'iconos de menú recargados del módulo: {len(menus)}')

# 4b. datos de módulos: el XML del módulo dice de qué fichero sale cada imagen
cache_xml = {}


def fichero_de_modulo(registro, campo):
    for datos in env['ir.model.data'].search([('model', '=', registro._name), ('res_id', '=', registro.id)]):
        if datos.module not in cache_xml:
            ficheros = []
            manifiesto = get_manifest(datos.module) or {}
            for ruta in manifiesto.get('data', []) + manifiesto.get('demo', []):
                if ruta.endswith('.xml'):
                    try:
                        with file_open(f'{datos.module}/{ruta}', 'rb') as f:
                            ficheros.append(etree.parse(f))
                    except Exception:  # noqa: BLE001
                        pass
            cache_xml[datos.module] = ficheros
        for arbol in cache_xml[datos.module]:
            for rec in arbol.iter('record'):
                rid = rec.get('id', '')
                if rid not in (datos.name, f'{datos.module}.{datos.name}'):
                    continue
                for fld in rec.iter('field'):
                    if fld.get('name') == campo and fld.get('file'):
                        return fld.get('file'), fld.get('type')
    return None, None


LOGO = Path('/mnt/extra-addons/ODOO_CRM/demo/video/logo_mh.png')
CATALOGO_WEB = Path('/mnt/extra-addons/ODOO_CRM/data/districthome_products.json')


def foto_de_catalogo(producto):
    """Foto original del producto (catálogo de origen), casando por referencia."""
    import json
    import urllib.request
    plantilla = producto.product_tmpl_id if producto._name == 'product.product' else producto
    if producto._name == 'product.image':
        plantilla = producto.product_tmpl_id
    ref = (plantilla.default_code or '').strip().lower()
    if not ref or not CATALOGO_WEB.exists():
        return None
    for item in json.loads(CATALOGO_WEB.read_text(encoding='utf-8')):
        if (item.get('handle') or '').strip().lower() == ref and item.get('image_url'):
            try:
                with urllib.request.urlopen(item['image_url'], timeout=30) as r:
                    return r.read()
            except Exception:  # noqa: BLE001
                return None
    return None


recargados = soltados = 0
hechos = set()
for adj in perdidos():
    if not adj.exists():
        continue  # su registro ya se reescribió y Odoo cambió el adjunto
    if not adj.res_model or not adj.res_field or adj.res_model not in env:
        adj.unlink()
        soltados += 1
        continue
    registro = env[adj.res_model].sudo().with_context(active_test=False).browse(adj.res_id).exists()
    if not registro:
        adj.unlink()
        soltados += 1
        continue
    campo = adj.res_field
    # las variantes image_128/256/... se regeneran al escribir image_1920
    base = 'image_1920' if re.fullmatch(r'image_\d+', campo) and 'image_1920' in registro._fields else campo
    if registro._name == 'res.company' and base == 'logo_web':
        base = 'logo'
    if (registro._name, registro.id, base) in hechos:
        continue
    crudo = None
    ruta, _tipo = fichero_de_modulo(registro, base)
    if ruta:
        with file_open(ruta, 'rb') as f:
            crudo = f.read()
    elif LOGO.exists() and (registro._name, base) in {('website', 'logo'), ('website', 'favicon'),
                                                        ('res.company', 'logo')}:
        crudo = LOGO.read_bytes()
    elif registro._name == 'res.partner' and registro == compania.partner_id and LOGO.exists():
        crudo = LOGO.read_bytes()
    elif registro._name in ('product.template', 'product.image') and base == 'image_1920':
        crudo = foto_de_catalogo(registro)
    if crudo:
        # Odoo 20 ya no acepta bytes en campos binarios: pide un BinaryValue.
        registro.write({base: BinaryBytes(crudo)})
        hechos.add((registro._name, registro.id, base))
        recargados += 1
    else:
        descripcion = f'{adj.res_model}.{campo} id={adj.res_id} ({registro.display_name})'
        adj.unlink()
        soltados += 1
        nota(f'  sin origen recuperable, se suelta: {descripcion}')
env.flush_all()
quedan = perdidos()
nota(f'ficheros perdidos: recargados {recargados}, soltados {soltados}, quedan {len(quedan)}')

# ---------------------------------------------------------------- comprobación
problemas = []
if not eur.active:
    problemas.append('EUR sigue inactivo')
env.cr.execute("SELECT count(*) FROM sale_order WHERE currency_id <> %s", (eur.id,))
if env.cr.fetchone()[0]:
    problemas.append('quedan pedidos en otra moneda')
if env['res.users'].search([('share', '=', False)]).filtered(lambda u: not u.company_ids):
    problemas.append('quedan usuarios sin compañía')
if quedan:
    problemas.append(f'quedan {len(quedan)} adjuntos sin fichero')
if env['product.template'].search_count([('is_furniture', '=', True), ('is_storable', '=', False)]):
    problemas.append('quedan muebles no almacenables')
env.cr.execute("""SELECT count(*) FROM stock_quant q JOIN stock_location l ON l.id = q.location_id
                   WHERE l.usage = 'internal' AND q.quantity < 0""")
if env.cr.fetchone()[0]:
    problemas.append('quedan existencias negativas en ubicaciones internas')
env.cr.commit()
print('ARREGLOS_OK' if not problemas else 'ARREGLOS_CON_PROBLEMAS: ' + '; '.join(problemas))
