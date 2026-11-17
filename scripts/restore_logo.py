#!/usr/bin/env python3
"""Restaura el logo del sitio web (monograma MH) tras la perdida del filestore.

El logo original no existia en disco (en la captura del 29/09 ya salia roto);
se recupera desde el frame de cierre del video del proyecto, que es donde
esta la identidad de marca real.
"""
import base64
import re
import xmlrpc.client
from pathlib import Path

CREDS_PATH = Path('/root/.hermes/profiles/kavana/credenciales_muebles_lab.txt')
LOGO_PATH = Path('demo/video/logo_mh.png')
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
        raise SystemExit('ERROR: no se pudo autenticar')
    models = xmlrpc.client.ServerProxy(f'{LOCAL_URL}/xmlrpc/2/object')

    payload = base64.b64encode(LOGO_PATH.read_bytes()).decode('ascii')
    print(f'logo: {LOGO_PATH.stat().st_size} bytes -> base64 {len(payload)}')

    webs = models.execute_kw(creds['db'], uid, creds['password'], 'website', 'search_read',
                             [[]], {'fields': ['id', 'name']})
    for web in webs:
        models.execute_kw(creds['db'], uid, creds['password'], 'website', 'write',
                          [[web['id']], {'logo': payload}])
        print(f'escrito logo en website {web["id"]} ({web["name"]})')

    atts = models.execute_kw(creds['db'], uid, creds['password'], 'ir.attachment', 'search_read',
                             [[['res_model', '=', 'website'], ['name', '=', 'logo']]],
                             {'fields': ['id', 'res_id', 'mimetype', 'file_size']})
    for a in atts:
        print(f'attachment {a["id"]} website={a["res_id"]} {a["mimetype"]} {a["file_size"]}B')


if __name__ == '__main__':
    main()
