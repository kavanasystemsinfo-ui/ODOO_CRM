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
    'mail.message',
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

    def test_no_puede_escribir_en_ningun_modelo_del_panel(self):
        """La denegación vale para todos los modelos que el grupo lee, no solo crm.lead.

        Los permisos de Odoo se suman entre grupos y «Usuario interno» ya escribe en
        algunos modelos (actividades, líneas de movimiento de stock): por eso hay
        reglas globales que cierran la escritura solo para el grupo del panel.
        """
        self.lead.activity_schedule(
            act_type_xmlid='mail.mail_activity_data_todo', summary='Actividad de prueba')
        env = self.env(user=self.usuario)
        comprobados = 0
        for modelo in MODELOS_DEL_PANEL:
            existente = self.env[modelo].search([], limit=1)
            if not existente:
                continue
            registro = env[modelo].browse(existente.id)
            for operacion in ('create', 'write', 'unlink'):
                with self.subTest(modelo=modelo, operacion=operacion):
                    with self.assertRaises(AccessError):
                        registro.check_access(operacion)
            comprobados += 1
        self.assertGreaterEqual(comprobados, 8, 'muy pocos modelos con datos para comprobar')
        self.assertTrue(self.env['mail.activity'].search_count([]))

    def test_mail_message_solo_lee_mensajes_de_leads(self):
        """El score lee el chatter de los leads; el resto de mensajes no le incumbe.

        Usuario interno recibe de Mail permisos condicionados sobre mensajes. Sin
        restricción propia, el panel podría leer el chatter de clientes, pedidos o
        facturas y publicar mensajes. Aquí se prueban las cuatro operaciones.
        """
        del_lead = self.lead.message_post(body='Le adjunto la propuesta', message_type='comment',
                                          subtype_xmlid='mail.mt_comment')
        cliente = self.env['res.partner'].create({'name': 'Cliente de prueba'})
        del_cliente = cliente.message_post(body='Nota sobre el cliente', message_type='comment',
                                           subtype_xmlid='mail.mt_note')
        env = self.env(user=self.usuario)
        Mensajes = env['mail.message']

        visibles = Mensajes.search([('id', 'in', (del_lead.id, del_cliente.id))])
        self.assertEqual(visibles.ids, [del_lead.id])
        self.assertEqual(Mensajes.browse(del_lead.id).body, del_lead.body)
        with self.assertRaises(AccessError):
            Mensajes.browse(del_cliente.id).check_access('read')

        with self.assertRaises(AccessError):
            Mensajes.create({'model': 'crm.lead', 'res_id': self.lead.id,
                             'body': 'No debería poder', 'message_type': 'comment'})
        for operacion in ('write', 'unlink'):
            with self.subTest(operacion=operacion), self.assertRaises(AccessError):
                Mensajes.browse(del_lead.id).check_access(operacion)

    def test_el_score_se_calcula_con_el_usuario_del_panel(self):
        """La restricción de mail.message no rompe el cálculo que el panel necesita."""
        self.lead.message_post(body='Le adjunto la propuesta', message_type='comment',
                               subtype_xmlid='mail.mt_comment')
        self.env.invalidate_all()
        lead = self.env(user=self.usuario)['crm.lead'].browse(self.lead.id)
        self.assertTrue(lead.x_contacto_reciente)
