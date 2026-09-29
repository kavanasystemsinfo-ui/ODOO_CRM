#!/usr/bin/env python3
"""Carga las imágenes de los productos de District Home en Odoo."""

import base64
import json
import re
import sys
import time
import xmlrpc.client
from pathlib import Path

import requests

CREDS_PATH = Path('/root/.hermes/profiles/hermes2/credenciales_muebles_lab.txt')
DATA_PATH = Path('/root/.hermes/profiles/hermes2/ODOO_CRM/data/districthome_products.json')

def read_credentials():
    content = CREDS_PATH.read_text(encoding='utf-8')
    url = re.search(r'URL:\s*(\S+)', content).group(1)
    username = re.search(r'Usuario:\s*(\S+)', content).group(1)
    password = re.search(r'Contraseña:\s*(\S+)', content).group(1)
    db = re.search(r'Base de datos:\s*(\S+)', content).group(1)
    return url, db, username, password

def main():
    url, db, username, password = read_credentials()
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    if not uid:
        print('ERROR: no se pudo autenticar')
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

    with DATA_PATH.open(encoding='utf-8') as f:
        products = json.load(f)

    # Build mapping name -> id for active furniture products
    ids = models.execute_kw(
        db, uid, password, 'product.template', 'search',
        [[['categ_id.parent_id.name', '=', 'Muebles de Hogar'], ['active', '=', True]]]
    )
    records = models.execute_kw(
        db, uid, password, 'product.template', 'read',
        [ids, ['name']]
    )
    name_to_id = {r['name']: r['id'] for r in records}
    print(f'Productos activos de muebles en Odoo: {len(name_to_id)}')

    ok = 0
    skipped = 0
    errors = 0

    for i, item in enumerate(products, 1):
        title = item['title']
        image_url = item.get('image_url')
        product_id = name_to_id.get(title)
        if not product_id:
            print(f'[{i}/80] SKIP: no encontrado en Odoo -> {title}')
            skipped += 1
            continue
        if not image_url:
            print(f'[{i}/80] SKIP: sin imagen -> {title}')
            skipped += 1
            continue

        try:
            # Pedir a Shopify una versión reducida (800px de ancho)
            sep = '&' if '?' in image_url else '?'
            thumb_url = f'{image_url}{sep}width=800'
            resp = requests.get(thumb_url, timeout=30)
            resp.raise_for_status()
            encoded = base64.b64encode(resp.content).decode('ascii')
            models.execute_kw(
                db, uid, password, 'product.template', 'write',
                [[product_id], {'image_1920': encoded}]
            )
            ok += 1
            print(f'[{i}/80] OK: {title} ({len(resp.content)//1024} KB)')
        except Exception as exc:
            errors += 1
            print(f'[{i}/80] ERROR: {title} -> {exc}')
        time.sleep(0.1)

    print(f'\nResumen: {ok} imágenes cargadas, {skipped} omitidas, {errors} errores.')

if __name__ == '__main__':
    main()
