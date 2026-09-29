# -*- coding: utf-8 -*-
"""
Muebles, fase 3: alinear el modelo del modulo con el catalogo real y poner los
textos en espanol.

  1. El modelo propio `furniture.product` (el que ve el panel del laboratorio)
     se rellena con los mismos 80 productos que el catalogo real, con sus
     precios, material, medidas y estilo deducidos de la ficha original.
  2. Se reescriben las descripciones de venta en espanol, para que la tienda no
     mezcle ingles y espanol.
  3. Se genera de nuevo `data/furniture.product.csv` del modulo con estos datos,
     para que al reinstalar el modulo se cree exactamente esto.
  4. Se bautiza el almacen.
"""

import csv
import re
import unicodedata

SINGULAR = {
    'sofas': 'Sofá', 'mesas': 'Mesa', 'sillas': 'Silla', 'camas': 'Cama',
    'armarios': 'Armario', 'estanterias': 'Estantería', 'escritorios': 'Escritorio',
    'butacas': 'Butaca', 'mesitas': 'Mesita', 'recibidores': 'Recibidor',
    'bancos': 'Banco', 'colchones': 'Colchón', 'otros': 'Mueble',
}

MATERIALES = [
    ('burl', 'raíz de nogal'), ('walnut', 'nogal'), ('oak', 'roble'),
    ('travertine', 'travertino'), ('marble', 'mármol'), ('brass', 'latón'),
    ('steel', 'acero'), ('metal', 'metal'), ('glass', 'vidrio'),
    ('rattan', 'ratán'), ('cane', 'rejilla'), ('leather', 'piel'),
    ('velvet', 'terciopelo'), ('linen', 'lino'), ('teak', 'teca'),
    ('wood', 'madera'), ('mahogany', 'caoba'), ('bamboo', 'bambú'),
]

ESTILOS = [
    ('mid-century', 'vintage'), ('midcentury', 'vintage'), ('antique', 'antiguo'),
    ('traditional', 'clásico'), ('rustic', 'rústico'), ('contemporary', 'contemporáneo'),
    ('modern', 'moderno'), ('minimal', 'minimalista'), ('sculptural', 'escultural'),
]


def paso(texto):
    print(texto, flush=True)


def sin_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto)
                   if unicodedata.category(c) != 'Mn')


def clasificar(texto, tabla, por_defecto):
    bajo = texto.lower()
    for clave, valor in tabla:
        if clave in bajo:
            return valor
    return por_defecto


def medidas(descripcion):
    patron = re.search(
        r'Width:\s*([\d.]+)"?.*?Height:\s*([\d.]+)"?.*?Depth:\s*([\d.]+)"?',
        descripcion, re.IGNORECASE | re.DOTALL)
    if not patron:
        return ''
    ancho, alto, fondo = (round(float(x) * 2.54) for x in patron.groups())
    return '%dx%dx%d' % (ancho, alto, fondo)


catalogo = env['product.template'].search([
    ('categ_id.parent_id.name', '=', 'Muebles de Hogar'),
    ('active', '=', True)], order='name')
paso("productos del catalogo real: %d" % len(catalogo))

modelo = env['furniture.product']
borrados = modelo.search([]).unlink()
paso("registros previos del modelo propio borrados: %d" % (borrados or 0))

filas = []
creados = 0
for indice, plantilla in enumerate(catalogo, start=1):
    texto = ' '.join(filter(None, [
        plantilla.name or '', plantilla.description_sale or '', plantilla.description or '']))
    clave_categoria = {
        'Sofás': 'sofas', 'Mesas': 'mesas', 'Sillas': 'sillas', 'Camas': 'camas',
        'Armarios': 'armarios', 'Estanterías': 'estanterias', 'Escritorios': 'escritorios',
        'Butacas': 'butacas', 'Mesitas': 'mesitas', 'Recibidores': 'recibidores',
        'Bancos': 'bancos', 'Colchones': 'colchones',
    }.get(plantilla.categ_id.name, 'otros')
    material = clasificar(texto, MATERIALES, 'madera')
    estilo = clasificar(texto, ESTILOS, 'moderno')
    dimensiones = medidas(plantilla.description_sale or plantilla.description or '')
    nombre = SINGULAR.get(clave_categoria, 'Mueble')
    garantia = 24
    descripcion = '%s de estilo %s fabricado en %s.' % (nombre, estilo, material)
    if dimensiones:
        descripcion += ' Dimensiones: %s cm.' % dimensiones
    descripcion += ' Garantía de %d meses.' % garantia

    valores = {
        'name': plantilla.name,
        'category': clave_categoria,
        'list_price': round(plantilla.list_price, 2),
        'standard_price': round(plantilla.standard_price, 2),
        'qty_available': int(round(plantilla.qty_available)),
        'material': material.capitalize(),
        'dimensions': dimensiones,
        'style': estilo.capitalize(),
        'warranty_months': garantia,
        'description': descripcion,
        'active': True,
    }
    try:
        with env.cr.savepoint():
            modelo.create(valores)
            creados += 1
            filas.append(('furniture_product_%03d' % indice, valores))
    except Exception as exc:
        paso("  aviso %s: %s" % (plantilla.name, str(exc)[:70]))

    try:
        with env.cr.savepoint():
            plantilla.write({'description_sale': descripcion})
    except Exception as exc:
        paso("  aviso descripcion %s: %s" % (plantilla.name, str(exc)[:60]))
env.cr.commit()
paso("registros creados en el modelo propio: %d" % creados)

# ------------------------------------------------------------- el CSV
ruta = '/mnt/extra-addons/ODOO_CRM/data/furniture.product.csv'
with open(ruta, 'w', newline='', encoding='utf-8') as fichero:
    escritor = csv.writer(fichero, lineterminator='\r\n')
    escritor.writerow(['id', 'name', 'category', 'list_price', 'standard_price',
                       'qty_available', 'material', 'dimensions', 'style',
                       'warranty_months', 'description'])
    for identificador, valores in filas:
        escritor.writerow([
            identificador, valores['name'], valores['category'], valores['list_price'],
            valores['standard_price'], valores['qty_available'], valores['material'],
            valores['dimensions'], valores['style'], valores['warranty_months'],
            valores['description']])
paso("CSV del modulo regenerado con %d filas" % len(filas))

# ------------------------------------------------------------- almacen
almacen = env['stock.warehouse'].search([], limit=1)
paso("almacen: %s" % almacen.name)
almacen.write({'name': 'Almacén central Muebles del Hogar'})
env.cr.commit()

paso("")
paso("=== MUESTRA ===")
for registro in modelo.search([], limit=4):
    paso("  %-34s %-12s %8.2f EUR  stock %3d  %s" % (
        registro.name, registro.category, registro.list_price,
        registro.qty_available, registro.description[:60]))
paso("total en el modelo propio: %d" % modelo.search_count([]))
