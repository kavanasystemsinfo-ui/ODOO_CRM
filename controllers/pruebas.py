"""Copias por visitante: probar la demo con libertad sin tocar la demo.

Recorrido:
  1. /probar (Odoo de la demo): explica y ofrece el botón. Al pulsarlo
     (POST), clona la plantilla en una base nueva «muebles_demo_xxxxxxxx»,
     anota en la propia base cuándo caduca y deja una cookie firmada.
  2. Con esa cookie, el proxy (Caddy) manda todas las peticiones al Odoo de
     pruebas (otro proceso, sin tareas programadas, que solo ve esas bases).
  3. /probar/entrar (Odoo de pruebas, sin base: lo carga como módulo de
     servidor): verifica la cookie y abre la sesión del usuario «probador» en
     esa copia, igual que /demo abre la de visita, sin contraseña.
  4. A la hora caduca la cookie y el navegador vuelve a la demo. Cinco minutos
     después, panel/limpiar_pruebas.py borra la copia.

El Odoo de la demo nunca carga una copia en memoria: crea la base con SQL y
copia sus ficheros. Solo lo hace el Odoo de pruebas, que se reinicia al
quedarse vacío.
"""
from __future__ import annotations

import html
import os
import shutil
import time
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2

import odoo
from odoo import SUPERUSER_ID, api, http
from odoo.http import request
from odoo.http.router import db_filter
from odoo.http.session import finalize, logout
from odoo.tools import config

from ..models import pruebas_firma as firma

ESTILO = """<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:48px auto;
padding:0 16px;color:#1f2937;line-height:1.5}h1{font-size:1.6rem}.boton{display:inline-block;
background:#714b67;color:#fff;border:0;border-radius:6px;padding:10px 18px;font-size:1rem;
text-decoration:none;cursor:pointer}.suave{color:#6b7280}ul{padding-left:1.2rem}</style>"""


def _secreto() -> str:
    return os.environ.get('MUEBLES_SECRETO', '').strip()


def _hora(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, ZoneInfo('Europe/Madrid')).strftime('%H:%M')


def _pagina(titulo: str, cuerpo: str, estado: int = 200):
    contenido = (f'<!doctype html><html lang="es"><head><meta charset="utf-8">'
                 f'<meta name="viewport" content="width=device-width,initial-scale=1">'
                 f'<title>{html.escape(titulo)}</title>{ESTILO}</head><body>'
                 f'<h1>{html.escape(titulo)}</h1>{cuerpo}</body></html>')
    return request.make_response(contenido, headers=[('Content-Type', 'text/html; charset=utf-8')],
                                 status=estado)


def _copias(cr) -> dict[str, int]:
    """Copias que existen y cuándo caduca cada una (lo dice su comentario)."""
    cr.execute("""
        SELECT datname, shobj_description(oid, 'pg_database')
          FROM pg_database WHERE datname LIKE %s
    """, (firma.PREFIJO + '%',))
    return {nombre: firma.leer_caducidad(texto) for nombre, texto in cr.fetchall()
            if firma.nombre_valido(nombre)}


def _es_odoo_de_pruebas() -> bool:
    return bool(config['dbfilter']) and 'muebles_demo_' in config['dbfilter']


class Pruebas(http.Controller):

    @http.route('/probar', type='http', auth='public', methods=['GET'], sitemap=False)
    def probar(self, **kwargs):
        if _es_odoo_de_pruebas():
            return request.redirect('/probar/entrar')
        if not _secreto():
            return _pagina('Pruebas no disponibles',
                           '<p>Este servidor no tiene activadas las copias de prueba.</p>', 503)
        return _pagina('Prueba la demo con libertad', f"""
<p>Te preparamos una <b>copia privada</b> de la empresa de demostración. En ella eres
responsable de ventas, compras, almacén y facturación: puedes crear clientes,
presupuestos y pedidos, confirmar, entregar, facturar y cobrar.</p>
<ul><li>Dura <b>{firma.DURACION // 60} minutos</b>. Después se borra entera.</li>
<li>Nada de lo que hagas llega a la demo pública ni a otros visitantes.</li>
<li>Es una base de pruebas: no sale ningún correo.</li>
<li>Hay {firma.TOPE} plazas a la vez; si están ocupadas, te diremos cuándo vuelve a haber.</li></ul>
<form method="post" action="/probar/crear">
<input type="hidden" name="csrf_token" value="{request.csrf_token()}">
<button class="boton" type="submit">Crear mi copia</button></form>
<p class="suave">¿Solo quieres mirar? <a href="/demo">Abre el escaparate de solo lectura</a>.</p>""")

    @http.route('/probar/crear', type='http', auth='public', methods=['POST'], sitemap=False)
    def crear(self, **kwargs):
        if _es_odoo_de_pruebas():
            return request.redirect('/probar/entrar')
        secreto = _secreto()
        if not secreto:
            return request.redirect('/probar')
        ahora = time.time()
        if firma.verificar(request.httprequest.cookies.get(firma.COOKIE), secreto, ahora):
            return request.redirect('/probar/entrar')  # ya tiene una copia en marcha

        nombre = firma.nuevo_nombre()
        caduca = int(ahora) + firma.DURACION
        sistema = odoo.sql_db.db_connect(config['db_system'])
        with closing(sistema.cursor()) as cr:
            cr._cnx.autocommit = True
            copias = _copias(cr)
            if firma.plazas_ocupadas(copias, ahora) >= firma.TOPE:
                minutos = firma.libre_en_minutos(copias, ahora)
                return _pagina('Las plazas de prueba están ocupadas', f"""
<p>Ahora mismo hay {firma.TOPE} personas probando la demo, que es lo que cabe en este
servidor. La próxima plaza queda libre en unos <b>{minutos} minutos</b>.</p>
<p><a class="boton" href="/demo">Mientras, mira el escaparate</a></p>""", 429)
            for intento in range(5):  # la plantilla se renueva a veces: un momento y otra vez
                try:
                    cr.execute(f'CREATE DATABASE "{nombre}" TEMPLATE "{firma.PLANTILLA}"')
                    break
                except (psycopg2.errors.ObjectInUse, psycopg2.errors.InvalidCatalogName):
                    if intento == 4:
                        return _pagina('No se pudo crear tu copia',
                                       '<p>Inténtalo de nuevo en un minuto.</p>', 503)
                    time.sleep(2)
            cr.execute(f'COMMENT ON DATABASE "{nombre}" IS %s', (firma.comentario(caduca),))
        origen, destino = config.filestore(firma.PLANTILLA), config.filestore(nombre)
        if os.path.isdir(origen) and not os.path.exists(destino):
            shutil.copytree(origen, destino)

        respuesta = request.redirect('/probar/entrar')
        respuesta.set_cookie(firma.COOKIE, firma.firmar(nombre, caduca, secreto),
                             max_age=firma.DURACION, secure=True, httponly=True,
                             samesite='Lax', path='/')
        return respuesta

    @http.route('/probar/entrar', type='http', auth='none', methods=['GET'], sitemap=False)
    def entrar(self, **kwargs):
        """Solo en el Odoo de pruebas, donde ODOO_CRM se carga como módulo de servidor."""
        prueba = firma.verificar(request.httprequest.cookies.get(firma.COOKIE), _secreto())
        if not prueba or not _es_odoo_de_pruebas() or not db_filter([prueba[0]]):
            respuesta = _pagina('Tu prueba ha terminado', """
<p>La copia caducó o ya no existe. Puedes crear otra cuando quieras.</p>
<p><a class="boton" href="/probar">Crear otra copia</a> &nbsp;
<a href="/demo">Ver el escaparate</a></p>""")
            respuesta.delete_cookie(firma.COOKIE, path='/')
            return respuesta
        nombre, caduca = prueba
        if request.session.db != nombre or not request.session.uid:
            registro = odoo.modules.registry.Registry(nombre)
            with registro.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                probador = env['res.users'].search([('login', '=', 'probador')], limit=1)
                if not probador:
                    return _pagina('Copia incompleta', '<p>Crea otra copia, por favor.</p>', 500)
                request.session['pre_login'] = probador.login
                request.session['pre_uid'] = probador.id
                finalize(request.session, env(user=None, su=False))
        return _pagina('Tu copia está lista', f"""
<p>Es tuya hasta las <b>{_hora(caduca)}</b> (hora de Madrid). Entras como
<b>Probador</b>, con permisos de ventas, compras, almacén y facturación.</p>
<p>Ideas para empezar: crea un presupuesto, confírmalo, valida la entrega y factúralo;
o compra a un proveedor y recibe la mercancía. La barra superior te recuerda que
estás en una base de pruebas.</p>
<p><a class="boton" href="/odoo">Entrar en Odoo</a> &nbsp;
<a href="/probar/salir">Terminar la prueba ahora</a></p>""")

    @http.route('/probar/salir', type='http', auth='none', methods=['GET'], sitemap=False)
    def salir(self, **kwargs):
        prueba = firma.verificar(request.httprequest.cookies.get(firma.COOKIE), _secreto())
        if prueba and _es_odoo_de_pruebas():
            sistema = odoo.sql_db.db_connect(config['db_system'])
            with closing(sistema.cursor()) as cr:  # caduca ya: la limpieza la borra enseguida
                cr._cnx.autocommit = True
                cr.execute(f'COMMENT ON DATABASE "{prueba[0]}" IS %s',
                           (firma.comentario(int(time.time()) - firma.GRACIA),))
        logout(request.session)
        respuesta = _pagina('Prueba terminada', """
<p>Tu copia se borrará en unos minutos. Gracias por probar la demo.</p>
<p><a class="boton" href="/demo">Volver al escaparate</a></p>""")
        respuesta.delete_cookie(firma.COOKIE, path='/')
        return respuesta
