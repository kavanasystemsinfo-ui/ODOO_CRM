# -*- coding: utf-8 -*-
"""
Muebles, fase 11: remates que se vieron al grabar el video.

Revisando las capturas para el video salieron cinco cosas feas, todas de la
demo de Odoo y todas visibles para cualquiera:

1. El logo de la tienda salia roto (el adjunto no esta en el filestore). Se
   genera un logo de laboratorio y se asigna a la empresa.
2. El telefono del sitio era "+1 555-555-5556" y el correo
   "info@sucompañia.example.com": estan escritos DENTRO de las plantillas del
   sitio, no en los datos de la empresa (que ya estaban en espanol).
3. La tienda abria con la "Tarifa distribuidores" en vez de la publica.
4. En el pie ponia "Nombre de la empresa".
5. Quedaban textos de la demo ("YourCompany") en plantillas.

Se hace por SQL sobre las plantillas (texto literal, no estructura) y por ORM
para el logo y la tarifa. Al final se avisa la cache para que el servidor en
marcha lo vea.
"""
import base64
import io


def cambiar_en_plantillas(viejo, nuevo):
    env.cr.execute("""
        UPDATE ir_ui_view
        SET arch_db = replace(arch_db::text, %s, %s)::jsonb
        WHERE arch_db::text LIKE %s
    """, (viejo, nuevo, '%' + viejo + '%'))
    filas = env.cr.rowcount
    print("   %-34s -> %-28s %3d plantillas" % (viejo[:34], nuevo[:28], filas))
    return filas


print("--- 1. logo de la empresa ---")
try:
    from PIL import Image, ImageDraw, ImageFont
    ancho, alto = 460, 110
    img = Image.new('RGBA', (ancho, alto), (255, 255, 255, 0))
    dib = ImageDraw.Draw(img)
    # marca: cuadro naranja con iniciales
    dib.rounded_rectangle([0, 8, 92, 100], radius=14, fill=(255, 112, 32, 255))
    fuente = None
    for ruta in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                 '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'):
        try:
            fuente = ImageFont.truetype(ruta, 44)
            fuente_texto = ImageFont.truetype(ruta, 30)
            break
        except Exception:
            continue
    if fuente is None:
        fuente = ImageFont.load_default()
        fuente_texto = fuente
    dib.text((46, 54), "MH", font=fuente, fill=(10, 10, 15, 255), anchor="mm")
    dib.text((112, 42), "MUEBLES DEL HOGAR", font=fuente_texto, fill=(10, 10, 15, 255), anchor="lm")
    dib.text((112, 74), "S.L.", font=fuente_texto, fill=(255, 112, 32, 255), anchor="lm")
    memoria = io.BytesIO()
    img.save(memoria, format='PNG')
    png = base64.b64encode(memoria.getvalue())
    print("   logo generado:", len(memoria.getvalue()), "bytes")
except Exception as error:
    png = False
    print("   OJO, no se pudo generar el logo:", error)

if png:
    empresa = env.company
    if 'logo' in empresa._fields:
        empresa.write({'logo': png})
        print("   logo asignado a la empresa (campo logo)")
    socio = empresa.partner_id
    for campo in ('image_1920', 'avatar_1920', 'image_1024'):
        if campo in socio._fields:
            socio.write({campo: png})
            print("   logo asignado al socio de la empresa:", campo)

print("--- 2. telefono, correo y textos de la demo en las plantillas ---")
cambios = 0
cambios += cambiar_en_plantillas('+1 555-555-5556', '+34 964 123 456')
cambios += cambiar_en_plantillas('info@sucompañía.example.com', 'info@mueblesdelhogar.example')
cambios += cambiar_en_plantillas('info@sucompania.example.com', 'info@mueblesdelhogar.example')
cambios += cambiar_en_plantillas('Nombre de la empresa', 'Muebles del Hogar S.L.')
cambios += cambiar_en_plantillas('YourCompany', 'Muebles del Hogar S.L.')
print("   plantillas tocadas en total:", cambios)

print("--- 3. tarifa publica en la tienda ---")
publica = env['product.pricelist'].search([('name', '=', 'Tarifa pública')], limit=1)
if not publica:
    publica = env['product.pricelist'].search([('name', 'in', ('EUR', 'Tarifa pública'))], limit=1)
print("   tarifa publica:", publica.id, publica.name)

env.cr.execute("SELECT id, res_id, value_reference FROM ir_property WHERE name = 'property_product_pricelist'")
for fila in env.cr.fetchall():
    print("   propiedad de tarifa:", fila)

env.cr.execute("""
    UPDATE ir_property SET value_reference = %s
    WHERE name = 'property_product_pricelist' AND value_reference <> %s
""", ('product.pricelist,%d' % publica.id, 'product.pricelist,%d' % publica.id))
print("   propiedades reasignadas a la tarifa publica:", env.cr.rowcount)

usuarios = env['res.users'].search([])
for u in usuarios:
    if u.partner_id.property_product_pricelist and u.partner_id.property_product_pricelist.id != publica.id:
        u.partner_id.property_product_pricelist = publica.id
        print("   socio %-42s -> tarifa publica" % u.partner_id.name[:42])

env.flush_all()
env.invalidate_all()
env.cr.commit()
env.registry.signal_changes()
env.cr.commit()

print("\n--- comprobacion ---")
env.cr.execute("SELECT count(*) FROM ir_ui_view WHERE arch_db::text LIKE '%555-555%' OR arch_db::text LIKE '%sucompa%' OR arch_db::text LIKE '%YourCompany%'")
print("plantillas con restos de la demo:", env.cr.fetchone()[0])
env.cr.execute("SELECT count(*) FROM ir_ui_view WHERE arch_db::text LIKE '%964 123 456%'")
print("plantillas con el telefono del laboratorio:", env.cr.fetchone()[0])
print("CONFIRMADO: logo, contacto, tarifa y textos de plantilla")
# -*- coding: utf-8 -*-
"""
Muebles, fase 12: arreglar el logo roto de la web.

El endpoint /web/image/website/1/logo devolvia 500. La causa esta en el
registro: hay adjuntos de la demo cuyo fichero NO existe en el filestore
(el volcado trae la fila del adjunto, pero no el fichero). Odoo intenta leerlo,
no lo encuentra y responde 500, asi que la tienda enseña una imagen rota.

Arreglo: borrar los adjuntos de logo/imagen de web y empresa cuyo fichero no
existe, y volver a escribir el logo para que Odoo cree adjunto y fichero nuevos.
"""
import base64
import io
import os

FILESTORE = '/var/lib/odoo/filestore/furniture_db'

env.cr.execute("""
    SELECT id, res_model, res_field, res_id, store_fname, file_size
    FROM ir_attachment
    WHERE store_fname IS NOT NULL
      AND (res_field ILIKE '%logo%' OR res_model IN ('website', 'res.company', 'res.partner'))
    ORDER BY id DESC
""")
adjuntos = env.cr.fetchall()
print("adjuntos de imagen revisados:", len(adjuntos))

rotos = []
for identificador, modelo, campo, registro, fichero, tamano in adjuntos:
    ruta = os.path.join(FILESTORE, fichero)
    if not os.path.exists(ruta):
        rotos.append((identificador, modelo, campo, registro, fichero))
print("adjuntos con fichero ausente:", len(rotos))
for r in rotos[:12]:
    print("   roto:", r[0], r[1], r[2], "->", r[4])

if rotos:
    ids = tuple(r[0] for r in rotos)
    env.cr.execute("DELETE FROM ir_attachment WHERE id IN %s", (ids,))
    print("adjuntos rotos retirados:", env.cr.rowcount)

# logo nuevo
from PIL import Image, ImageDraw, ImageFont
ancho, alto = 460, 110
img = Image.new('RGBA', (ancho, alto), (255, 255, 255, 0))
dib = ImageDraw.Draw(img)
dib.rounded_rectangle([0, 8, 92, 100], radius=14, fill=(255, 112, 32, 255))
fuente = fuente_texto = None
for ruta in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
             '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'):
    try:
        fuente = ImageFont.truetype(ruta, 44)
        fuente_texto = ImageFont.truetype(ruta, 30)
        break
    except Exception:
        continue
if fuente is None:
    fuente = fuente_texto = ImageFont.load_default()
dib.text((46, 54), "MH", font=fuente, fill=(10, 10, 15, 255), anchor="mm")
dib.text((112, 42), "MUEBLES DEL HOGAR", font=fuente_texto, fill=(10, 10, 15, 255), anchor="lm")
dib.text((112, 74), "S.L.", font=fuente_texto, fill=(255, 112, 32, 255), anchor="lm")
memoria = io.BytesIO()
img.save(memoria, format='PNG')
png = base64.b64encode(memoria.getvalue())

empresa = env.company
empresa.write({'logo': png})
empresa.partner_id.write({'image_1920': png})
env.flush_all()
env.cr.commit()
print("logo reescrito")

env.cr.execute("""
    SELECT id, res_model, res_field, store_fname FROM ir_attachment
    WHERE res_field ILIKE '%logo%' OR (res_model = 'res.company')
    ORDER BY id DESC LIMIT 6
""")
for fila in env.cr.fetchall():
    existe = os.path.exists(os.path.join(FILESTORE, fila[3] or ''))
    print("   adjunto %s %s/%s fichero presente: %s" % (fila[0], fila[1], fila[2], existe))

env.registry.signal_changes()
env.cr.commit()
print("CONFIRMADO: logo nuevo con su fichero en el filestore")
# -*- coding: utf-8 -*-
"""
Muebles, fase 13: logo legible y tarifa publica de verdad.

Dos cosas que se vieron al revisar la captura de la tienda:

1. El logo anterior tenia el nombre en texto pequeno dentro de una imagen
   apaisada; la cabecera lo muestra a 32-40 px de alto, asi que el texto quedaba
   ilegible y parecia una mancha. Se sustituye por una marca cuadrada y gruesa
   (cuadro naranja con las iniciales), legible a ese tamano.
2. La tienda abria con la tarifa de distribuidores. La tarifa publica era la
   unica "seleccionable", pero el usuario publico tenia asignada la otra: hay
   que reasignar la propiedad en el socio del usuario publico (y en el de la
   empresa), no solo en los usuarios normales.
"""
import base64
import io

env.cr.execute("""
    SELECT id, res_model, res_field, res_id, store_fname
    FROM ir_attachment WHERE res_field ILIKE '%logo%' ORDER BY id DESC LIMIT 5
""")
print("adjuntos de logo antes:", [f[0] for f in env.cr.fetchall()])

# --- 1. logo cuadrado y legible -----------------------------------------
from PIL import Image, ImageDraw, ImageFont

lado = 256
img = Image.new('RGBA', (lado, lado), (255, 255, 255, 0))
dib = ImageDraw.Draw(img)
dib.rounded_rectangle([6, 6, lado - 6, lado - 6], radius=48, fill=(255, 112, 32, 255))
fuente = None
for ruta in ('/usr/share/fonts/truetype/lato/Lato-Black.ttf',
             '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
             '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'):
    try:
        fuente = ImageFont.truetype(ruta, 118)
        print("fuente del logo:", ruta)
        break
    except Exception:
        continue
if fuente is None:
    fuente = ImageFont.load_default()
dib.text((lado / 2, lado / 2 - 4), "MH", font=fuente, fill=(12, 12, 18, 255), anchor="mm")
memoria = io.BytesIO()
img.save(memoria, format='PNG')
png = base64.b64encode(memoria.getvalue())
print("logo cuadrado generado:", len(memoria.getvalue()), "bytes")

empresa = env.company
empresa.write({'logo': png})
empresa.partner_id.write({'image_1920': png})

# --- 2. tarifa publica ---------------------------------------------------
publica = env['product.pricelist'].search([('name', '=', 'Tarifa pública')], limit=1)
print("tarifa publica:", publica.id, publica.name)

socios = env['res.users'].search([]).mapped('partner_id')
publico = env.ref('base.public_user', raise_if_not_found=False)
if publico:
    socios |= publico.partner_id
    print("usuario publico:", publico.login, "| tarifa antes:", publico.partner_id.property_product_pricelist.name)

for socio in socios:
    actual = socio.property_product_pricelist
    if actual and actual.id != publica.id:
        socio.property_product_pricelist = publica.id
        print("   %-44s %s -> Tarifa pública" % (socio.name[:44], actual.name))

env.flush_all()
env.invalidate_all()
env.cr.commit()
env.registry.signal_changes()
env.cr.commit()

print("\n--- comprobacion ---")
for usuario in env['res.users'].search([]):
    print("  %-30s tarifa: %s" % (usuario.login, usuario.partner_id.property_product_pricelist.name or '-'))
if publico:
    print("  %-30s tarifa: %s" % (publico.login, publico.partner_id.property_product_pricelist.name or '-'))
print("CONFIRMADO: logo legible y tarifa publica")
# -*- coding: utf-8 -*-
"""
Muebles, fase 14: el logo que se ve en la web.

Fallo de fondo, que costo tres intentos: `res.company.logo` es un campo
RELACIONADO con `partner_id.image_1920`, pero el logo que pinta la cabecera del
sitio es `website.logo`, un campo propio de la web (con su propio adjunto). Al
escribir solo en la empresa, la web seguia sirviendo su logo por defecto (el
icono gris de marcador).

Se escribe en los dos sitios: `website.logo` (lo que se ve) y el logo de la
empresa (lo que usan los informes).
"""
import base64
import io

from PIL import Image, ImageDraw, ImageFont

lado = 256
img = Image.new('RGBA', (lado, lado), (255, 255, 255, 0))
dib = ImageDraw.Draw(img)
dib.rounded_rectangle([4, 4, lado - 4, lado - 4], radius=52, fill=(255, 112, 32, 255))
fuente = None
for ruta in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
             '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'):
    try:
        fuente = ImageFont.truetype(ruta, 150)
        break
    except Exception:
        continue
if fuente is None:
    fuente = ImageFont.load_default()
dib.text((lado / 2, lado / 2 - 6), "M", font=fuente, fill=(12, 12, 18, 255), anchor="mm")
memoria = io.BytesIO()
img.save(memoria, format='PNG')
png = base64.b64encode(memoria.getvalue())
print("logo generado:", len(memoria.getvalue()), "bytes | pixel (30,30):", img.getpixel((30, 30)))

webs = env['website'].search([])
print("webs:", [(w.id, w.name) for w in webs])
for web in webs:
    web.write({'logo': png})
    print("   logo escrito en la web", web.id)

env.company.write({'logo': png})
env.company.partner_id.write({'image_1920': png})

env.flush_all()
env.invalidate_all()
env.cr.commit()
env.registry.signal_changes()
env.cr.commit()

env.cr.execute("""
    SELECT id, res_model, res_field, res_id, file_size
    FROM ir_attachment
    WHERE res_field = 'logo' ORDER BY id DESC LIMIT 5
""")
for fila in env.cr.fetchall():
    print("   adjunto del logo:", fila)
print("CONFIRMADO: logo del sitio escrito")
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Escribe el logo del sitio POR XML-RPC.

Por que asi: los campos de imagen y binarios se guardan como adjunto + fichero
en el filestore. Si se escriben desde un contenedor de usar y tirar (odoo shell
lanzado con docker run), el fichero acaba en el disco efimero de ese contenedor y
se pierde: la base queda con el adjunto pero sin el fichero, y la web responde
500 o sirve un marcador vacio. Escribiendo por XML-RPC, el fichero lo guarda el
servidor que atiende, que es el que tiene el filestore de verdad.
"""
import base64
import io
import re
import xmlrpc.client
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CREDS = Path('/root/.hermes/profiles/hermes2/credenciales_muebles_lab.txt')

texto = CREDS.read_text(encoding='utf-8')
url = re.search(r'URL:\s*(\S+)', texto).group(1)
bd = re.search(r'Base de datos:\s*(\S+)', texto).group(1)
usuario = re.search(r'Usuario:\s*(\S+)', texto).group(1)
clave = re.search(r'Contraseña:\s*(\S+)', texto).group(1)

# --- logo: cuadro naranja con una M gruesa, legible a 40 px ---
lado = 256
img = Image.new('RGBA', (lado, lado), (255, 255, 255, 0))
dib = ImageDraw.Draw(img)
dib.rounded_rectangle([4, 4, lado - 4, lado - 4], radius=52, fill=(255, 112, 32, 255))
fuente = None
for ruta in ('/usr/share/fonts/truetype/lato/Lato-Black.ttf',
             '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
             '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'):
    try:
        fuente = ImageFont.truetype(ruta, 150)
        print('fuente del logo:', ruta)
        break
    except Exception:
        continue
if fuente is None:
    fuente = ImageFont.load_default()
dib.text((lado / 2, lado / 2 - 6), "M", font=fuente, fill=(12, 12, 18, 255), anchor="mm")
memoria = io.BytesIO()
img.save(memoria, format='PNG')
png = base64.b64encode(memoria.getvalue()).decode('ascii')
print('logo:', len(memoria.getvalue()), 'bytes | pixel (30,30):', img.getpixel((30, 30)))

comun = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = comun.authenticate(bd, usuario, clave, {})
modelos = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
print('autenticado:', bool(uid))

webs = modelos.execute_kw(bd, uid, clave, 'website', 'search', [[]])
print('webs:', webs)
modelos.execute_kw(bd, uid, clave, 'website', 'write', [webs, {'logo': png}])

empresa = modelos.execute_kw(bd, uid, clave, 'res.company', 'search', [[['id', '=', 1]]])
modelos.execute_kw(bd, uid, clave, 'res.company', 'write', [empresa, {'logo': png}])
print('logo escrito en la web y en la empresa via XML-RPC')

# comprobacion: leer el adjunto y su tamaño
adjuntos = modelos.execute_kw(bd, uid, clave, 'ir.attachment', 'search_read',
                              [[['res_field', '=', 'logo']], ['id', 'res_model', 'res_id', 'file_size']])
for a in adjuntos:
    print('   adjunto', a['id'], a['res_model'], a['res_id'], a['file_size'], 'bytes')
