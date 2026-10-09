"""Herencia de crm.lead: señales del sector y score determinista.

El score NO se guarda: se recalcula al leer (campo computed no stored), así
una oportunidad con contacto de hace un mes no conserva el punto de
"contacto reciente". La prioridad se sugiere en un campo; aplicarla
(cambiar priority de la oportunidad) sigue siendo decisión del comercial.
"""
from __future__ import annotations

from odoo import fields, models

from . import lead_scoring


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
    x_contacto_reciente = fields.Boolean(
        string='Contacto en 7 días',
        compute='_compute_x_contacto_reciente',
        help='Hubo actividad con el cliente en los últimos 7 días.',
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

    def _compute_x_contacto_reciente(self):
        hoy = fields.Date.context_today(self)
        for lead in self:
            actividades = lead.activity_ids.filtered(
                lambda a: a.state in ('today', 'planned') or a.date_done
            )
            fecha = max(
                (a.date_deadline for a in actividades if a.date_deadline),
                default=None,
            )
            lead.x_contacto_reciente = bool(
                fecha and (hoy - fecha).days <= 7
            )

    def _compute_x_email_corporativo(self):
        for lead in self:
            lead.x_email_corporativo = lead_scoring.es_email_corporativo(
                lead.partner_id.email or lead.email_from
            )

    def _compute_x_score_kavana(self):
        for lead in self:
            score = lead_scoring.puntuar(lead._senales())
            lead.x_score_kavana = score
            lead.x_prioridad_sugerida = lead_scoring.prioridad_sugerida(score)
