#!/usr/bin/env python3
"""Restaura las imagenes del catalogo tras la perdida del filestore.

Casa por REFERENCIA (default_code = handle del JSON), igual que el script
original load_product_images.py. Diferencias: habla con Odoo por
http://127.0.0.1:8070 (el dominio del fichero de credenciales no sirve TLS
en este VPS) y solo rellena productos SIN imagen, para no pisar nada.
"""
import base64
import json
import re
import sys
import time
import xmlrpc.client
from pathlib import Path

import requests

CREDS_PATH = Path('/root/.hermes/profiles/kavana/credenciales_muebles_lab.txt')
DATA_PATH = Path('/root/.hermes/profiles/kavana/ODOO_CRM/data/districthome_products.json')
LOCAL_URL = 'http://127.0.0.1:8070'


def read_credentials():
    content = CREDS_PATH.read_text(encoding='utf-8')
    return {
        'db': re.search(r'Base de datos:\s*(\S+)', content).group(1),
        'user': re.search(r'Usuario:\s*(\S+)', content).group(1),
        'password': re.search(r'Contraseña:\s*(\S+)', content).group(1),
    }


def main():
    creds = read_credentials()
    common = xmlrpc.client.ServerProxy(f'{LOCAL_URL}/xmlrpc/2/common')
    uid = common.authenticate(creds['db'], creds['user'], creds['password'], {})
    if not uid:
        print('ERROR: no se pudo autenticar')
        sys.exit(1)
    models = xmlrpc.client.ServerProxy(f'{LOCAL_URL}/xmlrpc/2/object')

    products = json.load(DATA_PATH.open(encoding='utf-8'))

    ids = models.execute_kw(creds['db'], uid, creds['password'], 'product.template', 'search',
                            [[['active', '=', True]]])
    records = models.execute_kw(creds['db'], uid, creds['password'], 'product.template', 'read',
                                [ids, ['default_code', 'name', 'image_1920']])
    ref_to_product = {r['default_code'].strip().lower(): r for r in records if r.get('default_code')}
    print(f'Productos activos con referencia: {len(ref_to_product)}')

    ok = restored = skipped = errors = 0
    for i, item in enumerate(products, 1):
        handle = (item.get('handle') or '').strip().lower()
        image_url = item.get('image_url')
        product = ref_to_product.get(handle)
        tag = f'[{i}/{len(products)}]'
        if not product:
            print(f'{tag} SKIP: sin producto para {handle!r} ({item["title"]})')
            skipped += 1
            continue
        if not image_url:
            print(f'{tag} SKIP: sin imagen -> {item["title"]}')
            skipped += 1
            continue
        if product.get('image_1920'):
            ok += 1
            continue
        try:
            sep = '&' if '?' in image_url else '?'
            resp = requests.get(f'{image_url}{sep}width=800', timeout=30)
            resp.raise_for_status()
            models.execute_kw(creds['db'], uid, creds['password'], 'product.template', 'write',
                              [[product['id']],
                               {'image_1920': base64.b64encode(resp.content).decode('ascii')}])
            restored += 1
            print(f'{tag} RESTAURADA: {item["title"]} ({len(resp.content) // 1024} KB)')
        except Exception as exc:
            errors += 1
            print(f'{tag} ERROR: {item["title"]} -> {exc}')
        time.sleep(0.1)

    print(f'\nResumen: {restored} restauradas, {ok} ya tenian imagen, {skipped} omitidas, {errors} errores.')


if __name__ == '__main__':
    main()
