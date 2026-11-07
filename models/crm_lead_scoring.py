"""Herencia de crm.lead: señales del sector y score determinista.

El score NO se guarda: se recalcula al leer (campo computed no stored), así
una oportunidad con contacto de hace un mes no conserva el punto de
"contacto reciente". La prioridad se sugiere en un campo; aplicarla
(cambiar priority de la oportunidad) sigue siendo decisión del comercial.

Cada campo calculado declara sus dependencias (`@api.depends`): si cambia una
señal dentro de la misma transacción, Odoo invalida la caché y el score se
recalcula. Sin ellas el formulario y el código veían el score viejo.

"Contacto reciente" significa que se habló con el cliente, no que haya una
tarea apuntada: cuenta el último correo, el último mensaje enviado desde el
chatter y la última actividad marcada como hecha. Una llamada planificada para
mañana o una nota interna no son contacto.
"""
from __future__ import annotations

from datetime import timedelta

from odoo import api, fields, models

from . import lead_scoring

DIAS_CONTACTO_RECIENTE = 7


class CrmLeadScoring(models.Model):
    _inherit = 'crm.lead'

    x_es_contrato = fields.Boolean(
        string='Cliente contract/estudio',
        help='Marca si el lead es de contract, interiorismo o distribución (compra en serie).',
    )
    x_proyecto_referenciado = fields.Boolean(
        string='Proyecto referenciado',
        help='Hay un número de proyecto o referencia de obra en la conversación.',
    )
    x_muestra_pedida = fields.Boolean(
        string='Muestra pedida',
        help='El cliente pidió ver catálogo físico o muestra de material.',
    )
    x_fecha_ultimo_contacto = fields.Datetime(
        string='Último contacto real',
        compute='_compute_x_fecha_ultimo_contacto',
        help='Último correo, mensaje enviado al cliente o actividad hecha. '
             'Las notas internas y las actividades pendientes no cuentan.',
    )
    x_contacto_reciente = fields.Boolean(
        string=f'Contacto en {DIAS_CONTACTO_RECIENTE} días',
        compute='_compute_x_contacto_reciente',
        help=f'Hubo contacto real con el cliente en los últimos {DIAS_CONTACTO_RECIENTE} días.',
    )
    x_email_corporativo = fields.Boolean(
        string='Email corporativo',
        compute='_compute_x_email_corporativo',
        help='El email del contacto no es de un proveedor gratuito.',
    )
    x_score_kavana = fields.Integer(
        string='Score Kavana (0-100)',
        compute='_compute_x_score_kavana',
        help='Puntuación determinista: cada señal vale lo que la tabla de '
             'lead_scoring.PESOS dice. Explicable, sin IA ni azar.',
    )
    x_prioridad_sugerida = fields.Selection([
        ('ninguna', 'Ninguna'),
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
    ], string='Prioridad sugerida',
        compute='_compute_x_score_kavana',
        help='Sugerencia a partir del score; aplicarla es cosa del comercial.',
    )

    def _senales(self) -> dict[str, bool]:
        """Las cinco señales como diccionario para la función pura."""
        self.ensure_one()
        return {
            'tipo_contrato': bool(self.x_es_contrato),
            'proyecto_referenciado': bool(self.x_proyecto_referenciado),
            'muestra_pedida': bool(self.x_muestra_pedida),
            'email_corporativo': bool(self.x_email_corporativo),
            'contacto_reciente': bool(self.x_contacto_reciente),
        }

    @api.model
    def _es_contacto_real(self, mensaje) -> bool:
        """Un mensaje cuenta como contacto si llegó o salió hacia el cliente."""
        if mensaje.mail_activity_type_id:  # actividad marcada como hecha
            return True
        if mensaje.message_type == 'email':
            return True
        nota_interna = self.env.ref('mail.mt_note', raise_if_not_found=False)
        return mensaje.message_type == 'comment' and mensaje.subtype_id != nota_interna

    @api.depends('message_ids.date', 'message_ids.message_type',
                 'message_ids.subtype_id', 'message_ids.mail_activity_type_id')
    def _compute_x_fecha_ultimo_contacto(self):
        for lead in self:
            fechas = [m.date for m in lead.message_ids if m.date and self._es_contacto_real(m)]
            lead.x_fecha_ultimo_contacto = max(fechas, default=False)

    @api.depends('x_fecha_ultimo_contacto')
    def _compute_x_contacto_reciente(self):
        limite = fields.Datetime.now() - timedelta(days=DIAS_CONTACTO_RECIENTE)
        for lead in self:
            lead.x_contacto_reciente = bool(
                lead.x_fecha_ultimo_contacto and lead.x_fecha_ultimo_contacto >= limite
            )

    @api.depends('partner_id.email', 'email_from')
    def _compute_x_email_corporativo(self):
        for lead in self:
            lead.x_email_corporativo = lead_scoring.es_email_corporativo(
                lead.partner_id.email or lead.email_from
            )

    @api.depends('x_es_contrato', 'x_proyecto_referenciado', 'x_muestra_pedida',
                 'x_email_corporativo', 'x_contacto_reciente')
    def _compute_x_score_kavana(self):
        for lead in self:
            score = lead_scoring.puntuar(lead._senales())
            lead.x_score_kavana = score
            lead.x_prioridad_sugerida = lead_scoring.prioridad_sugerida(score)
