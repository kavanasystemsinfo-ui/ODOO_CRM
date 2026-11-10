"""Escaparate de solo lectura: el visitante ve toda la empresa y no cambia nada.

La demo pública entra con el usuario «visita» (ruta /demo, sin contraseña).
Con el grupo «Escaparate: solo lectura», crear, modificar y borrar quedan
cerrados en TODOS los modelos, también en los de módulos que se instalen
mañana, sin listar uno a uno.

Cómo: en Odoo 20 todos los permisos (los antiguos ACL y reglas, ahora
ir.access) se resuelven en Model._access_domain(operación). Si para el
visitante ese dominio es «falso» en create/write/unlink, Odoo lo trata como
permiso inexistente en todas partes: has_access(), check_access() y la propia
interfaz, que abre los formularios en lectura y no ofrece «Nuevo» ni «Borrar».

Excepciones (lo que Odoo escribe solo con navegar, sin tocar datos de negocio):
  * asistentes (modelos transitorios): se abren, pero lo que intenten
    escribir en un modelo real vuelve a estar cerrado;
  * preferencias y presencia de la propia sesión (EXCEPCIONES).
Lo que Odoo escribe como superusuario (registro de accesos, assets) no pasa
por aquí.
"""
from __future__ import annotations

from odoo import _, api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain

GRUPO = 'ODOO_CRM.group_escaparate'
USUARIO_VISITA = 'visita'
FILTRO_TODO = 'Toda la empresa'
# Acciones que abren con «Mis oportunidades» o «Mis presupuestos». El visitante
# no es comercial: sin un favorito por defecto vería el embudo vacío.
ACCIONES_TODA_LA_EMPRESA = (
    'crm.crm_lead_action_pipeline', 'crm.crm_lead_action_forecast',
    'sale.action_quotations_with_onboarding', 'sale.action_quotations',
)

# Modelos técnicos que la interfaz escribe al navegar. Nada de negocio.
EXCEPCIONES = frozenset({
    'res.users.settings',          # preferencias de la interfaz (barra lateral, etc.)
    'res.users.settings.volumes',
    'res.users.log',
    'bus.presence',
    'mail.presence',
    'discuss.channel.member',      # estado plegado de las ventanas de chat
})


class EscaparateBase(models.AbstractModel):
    _inherit = 'base'

    def _escaparate_cerrado(self, operacion: str) -> bool:
        return (operacion != 'read'
                and not self.env.su
                and not self._transient
                and self._name not in EXCEPCIONES
                and self.env.user.has_group(GRUPO))

    @api.model
    def _access_domain(self, operation: str) -> Domain:
        if self._escaparate_cerrado(operation):
            return Domain.FALSE
        return super()._access_domain(operation)

    def _make_access_error_message(self, operation: str, domain: Domain) -> AccessError:
        if self._escaparate_cerrado(operation):
            modelo = self.env['ir.model'].sudo()._get(self._name).name or self._description
            return AccessError(_(
                'Estás en el escaparate de solo lectura de la demo: puedes ver todo, '
                'pero no crear, modificar ni borrar (%(modelo)s).', modelo=modelo))
        return super()._make_access_error_message(operation, domain)


class Escaparate(models.AbstractModel):
    _name = 'odoo_crm.escaparate'
    _description = 'Escaparate de solo lectura de la demo'

    @api.model
    def _preparar_visita(self) -> None:
        """Lo llama data/escaparate.xml en cada actualización del módulo.

        Pone al usuario de visita en el escaparate y le da lectura de
        contabilidad (grupo de Odoo «solo lectura»), para que vea facturas y
        cobros de la empresa simulada. Le quita «Características técnicas»: sin
        ser administrador, esos menús de Ajustes/Técnico fallan al abrirse y no
        enseñan nada del negocio.
        """
        visita = self.env['res.users'].with_context(active_test=False).search(
            [('login', '=', USUARIO_VISITA)], limit=1)
        if not visita:
            return
        grupos = self.env.ref(GRUPO)
        lectura_contable = self.env.ref('account.group_account_readonly', raise_if_not_found=False)
        if lectura_contable:
            grupos |= lectura_contable
        campo = 'group_ids' if 'group_ids' in visita._fields else 'groups_id'
        cambios = [(4, grupo.id) for grupo in grupos]
        tecnico = self.env.ref('base.group_no_one', raise_if_not_found=False)
        if tecnico:
            cambios.append((3, tecnico.id))
        visita.sudo().write({campo: cambios})
        self._filtros_toda_la_empresa(visita)

    @api.model
    def _filtros_toda_la_empresa(self, visita) -> None:
        Filtros = self.env['ir.filters'].sudo().with_context(active_test=False)
        for xmlid in ACCIONES_TODA_LA_EMPRESA:
            accion = self.env.ref(xmlid, raise_if_not_found=False)
            if not accion or Filtros.search_count([
                    ('action_id', '=', accion.id), ('user_ids', 'in', visita.id),
                    ('name', '=', FILTRO_TODO)]):
                continue
            Filtros.create({
                'name': FILTRO_TODO, 'model_id': accion.res_model, 'action_id': accion.id,
                'domain': '[]', 'context': '{}', 'is_default': True,
                'user_ids': [(6, 0, visita.ids)],
            })
