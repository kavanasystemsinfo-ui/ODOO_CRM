#!/usr/bin/env python3
"""Carga las imágenes de los productos de District Home en Odoo.

Casado por REFERENCIA (`default_code`), no por nombre: el catálogo del
laboratorio tiene los nombres en español y los títulos de origen están en
inglés, así que casar por nombre deja los 80 productos sin imagen.
"""
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

    ids = models.execute_kw(db, uid, password, 'product.template', 'search', [[['active', '=', True]]])
    records = models.execute_kw(db, uid, password, 'product.template', 'read', [ids, ['default_code', 'name']])
    ref_to_id = {}
    for r in records:
        if r.get('default_code'):
            ref_to_id[r['default_code'].strip().lower()] = r['id']
    print(f'Productos activos con referencia en Odoo: {len(ref_to_id)}')

    ok = skipped = errors = 0
    for i, item in enumerate(products, 1):
        handle = (item.get('handle') or '').strip().lower()
        image_url = item.get('image_url')
        product_id = ref_to_id.get(handle)
        if not product_id:
            print(f'[{i}/80] SKIP: sin producto para la referencia {handle!r} ({item["title"]})')
            skipped += 1
            continue
        if not image_url:
            print(f'[{i}/80] SKIP: sin imagen -> {item["title"]}')
            skipped += 1
            continue
        try:
            sep = '&' if '?' in image_url else '?'
            resp = requests.get(f'{image_url}{sep}width=800', timeout=30)
            resp.raise_for_status()
            models.execute_kw(db, uid, password, 'product.template', 'write',
                              [[product_id], {'image_1920': base64.b64encode(resp.content).decode('ascii')}])
            ok += 1
            print(f'[{i}/80] OK: {item["title"]} ({len(resp.content)//1024} KB)')
        except Exception as exc:
            errors += 1
            print(f'[{i}/80] ERROR: {item["title"]} -> {exc}')
        time.sleep(0.1)

    print(f'\nResumen: {ok} imágenes cargadas, {skipped} omitidas, {errors} errores.')


if __name__ == '__main__':
    main()
