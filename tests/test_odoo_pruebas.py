"""Copias de prueba por visitante: el portero en el Odoo de la demo."""
import re
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from ..models import pruebas_firma as firma

SECRETO = {'MUEBLES_SECRETO': 'secreto-de-prueba'}


@tagged('post_install', '-at_install', 'odoo_crm')
class TestPortero(HttpCase):

    def test_sin_secreto_no_hay_copias(self):
        with patch.dict('os.environ', {'MUEBLES_SECRETO': ''}):
            respuesta = self.url_open('/probar')
        self.assertEqual(respuesta.status_code, 503)

    def test_explica_y_ofrece_el_boton(self):
        with patch.dict('os.environ', SECRETO):
            respuesta = self.url_open('/probar')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('Crear mi copia', respuesta.text)
        self.assertIn('60 minutos', respuesta.text)
        self.assertIn('csrf_token', respuesta.text)

    def test_con_las_plazas_ocupadas_avisa_y_no_crea(self):
        with patch.dict('os.environ', SECRETO):
            pagina = self.url_open('/probar').text
            token = re.search(r'name="csrf_token" value="([^"]+)"', pagina).group(1)
            with patch.object(firma, 'TOPE', 0):
                respuesta = self.url_open('/probar/crear', data={'csrf_token': token},
                                          allow_redirects=False)
        self.assertEqual(respuesta.status_code, 429)
        self.assertIn('ocupadas', respuesta.text)
        self.assertNotIn(firma.COOKIE, respuesta.headers.get('Set-Cookie', ''))

    def test_crear_exige_post_con_csrf(self):
        with patch.dict('os.environ', SECRETO):
            respuesta = self.url_open('/probar/crear', data={}, allow_redirects=False)
        self.assertNotEqual(respuesta.status_code, 302)

    def test_en_el_odoo_de_la_demo_entrar_no_abre_nada(self):
        cookie = firma.firmar('muebles_demo_abcd1234', 4_000_000_000, SECRETO['MUEBLES_SECRETO'])
        self.opener.cookies.set(firma.COOKIE, cookie)
        with patch.dict('os.environ', SECRETO):
            respuesta = self.url_open('/probar/entrar')
        self.assertIn('terminado', respuesta.text)
