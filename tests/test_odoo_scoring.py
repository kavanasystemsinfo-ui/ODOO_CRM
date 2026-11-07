"""Scoring comercial dentro de Odoo (hallazgo 2.4 de la auditoría).

Dos defectos de la v1, cada uno con su prueba:
- los campos calculados no declaraban dependencias: al marcar una señal, el
  score seguía mostrando el valor viejo en la misma transacción;
- "contacto reciente" usaba la fecha límite de las actividades: una llamada
  planificada para mañana contaba como si ya se hubiera hablado.
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'odoo_crm')
class TestScoringComercial(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lead = cls.env['crm.lead'].create({
            'name': 'Reforma hotel Valencia',
            'type': 'opportunity',
            'email_from': 'compras@hotelvalencia.es',
        })

    def _refrescar(self):
        # Entre peticiones HTTP la caché siempre está limpia; en una prueba hay
        # que vaciarla a mano tras crear mensajes por otra vía.
        self.env.invalidate_all()

    def test_el_score_se_recalcula_al_cambiar_una_senal(self):
        self.assertEqual(self.lead.x_score_kavana, 10)  # solo email corporativo
        self.lead.x_muestra_pedida = True
        self.assertEqual(self.lead.x_score_kavana, 40)
        self.lead.x_es_contrato = True
        self.assertEqual(self.lead.x_score_kavana, 65)
        self.assertEqual(self.lead.x_prioridad_sugerida, 'media')

    def test_el_email_cambia_la_senal_corporativa(self):
        self.assertTrue(self.lead.x_email_corporativo)
        self.lead.email_from = 'pepe@gmail.com'
        self.assertFalse(self.lead.x_email_corporativo)

    def test_una_actividad_planificada_no_es_contacto(self):
        self.lead.activity_schedule(
            'mail.mail_activity_data_call',
            date_deadline=fields.Date.context_today(self.lead) + timedelta(days=1),
            summary='Llamar para enseñar muestras',
        )
        self._refrescar()
        self.assertFalse(self.lead.x_contacto_reciente)
        self.assertEqual(self.lead.x_score_kavana, 10)

    def test_una_nota_interna_no_es_contacto(self):
        self.lead.message_post(body='Parece interesado', message_type='comment',
                               subtype_xmlid='mail.mt_note')
        self._refrescar()
        self.assertFalse(self.lead.x_contacto_reciente)

    def test_un_mensaje_al_cliente_es_contacto(self):
        self.lead.message_post(body='Le adjunto la propuesta', message_type='comment',
                               subtype_xmlid='mail.mt_comment')
        self._refrescar()
        self.assertTrue(self.lead.x_contacto_reciente)
        self.assertEqual(self.lead.x_score_kavana, 25)

    def test_una_actividad_hecha_es_contacto(self):
        actividad = self.lead.activity_schedule(
            'mail.mail_activity_data_call',
            date_deadline=fields.Date.context_today(self.lead) - timedelta(days=1),
            summary='Llamada de seguimiento',
        )
        actividad.action_feedback(feedback='Confirma que quiere muestras')
        self._refrescar()
        self.assertTrue(self.lead.x_contacto_reciente)

    def test_un_contacto_antiguo_no_cuenta(self):
        mensaje = self.lead.message_post(body='Primer contacto', message_type='comment',
                                         subtype_xmlid='mail.mt_comment')
        mensaje.sudo().date = fields.Datetime.now() - timedelta(days=10)
        self._refrescar()
        self.assertFalse(self.lead.x_contacto_reciente)
        self.assertTrue(self.lead.x_fecha_ultimo_contacto)
