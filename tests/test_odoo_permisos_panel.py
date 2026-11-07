"""Usuario de integración del panel (hallazgo 2.2 de la auditoría).

El panel ya no entra por PostgreSQL: lee por JSON-RPC con un usuario que solo
tiene el grupo «Panel del día: solo lectura». Aquí se prueba que ese usuario
puede leer todo lo que el panel consulta y que no puede escribir nada.
"""
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

MODELOS_DEL_PANEL = [
    'product.template', 'product.product', 'product.category', 'res.partner',
    'sale.order', 'sale.order.line', 'purchase.order', 'purchase.order.line',
    'stock.picking', 'stock.picking.type', 'stock.quant', 'stock.location',
    'stock.move', 'stock.move.line', 'account.move', 'crm.lead', 'mail.activity',
]


@tagged('post_install', '-at_install', 'odoo_crm')
class TestUsuarioPanel(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.usuario = new_test_user(
            cls.env, login='panel_lectura_test',
            groups='base.group_user,ODOO_CRM.group_panel_lectura',
        )
        cls.lead = cls.env['crm.lead'].create({'name': 'Lead de prueba', 'type': 'opportunity'})

    def test_lee_todo_lo_que_consulta_el_panel(self):
        env = self.env(user=self.usuario)
        for modelo in MODELOS_DEL_PANEL:
            with self.subTest(modelo=modelo):
                env[modelo].search_count([])
        filas = env['crm.lead'].search_read(
            [('id', '=', self.lead.id)], ['x_score_kavana', 'x_prioridad_sugerida'])
        self.assertEqual(len(filas), 1)

    def test_la_clave_de_integracion_sirve_para_json2_y_dura_un_trimestre(self):
        """Odoo 20: JSON-2 solo acepta claves 'rpc' y limita su vida por grupo."""
        claves = self.env['res.users.apikeys'].with_user(self.usuario)
        clave = claves._generate('rpc', 'panel', fields.Datetime.now() + timedelta(days=60))
        self.assertEqual(
            self.env['res.users.apikeys']._check_credentials(scope='rpc', key=clave),
            self.usuario.id)
        with self.assertRaises(ValidationError):
            claves._generate('rpc', 'panel', fields.Datetime.now() + timedelta(days=200))

    def test_no_puede_crear_ni_modificar(self):
        env = self.env(user=self.usuario)
        with self.assertRaises(AccessError):
            env['crm.lead'].create({'name': 'No debería poder'})
        with self.assertRaises(AccessError):
            env['crm.lead'].browse(self.lead.id).write({'name': 'Cambiado'})
        with self.assertRaises(AccessError):
            env['crm.lead'].browse(self.lead.id).unlink()
