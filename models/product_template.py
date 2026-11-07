"""Ficha de mobiliario sobre el producto nativo de Odoo.

Hasta la versión 20.0.1.x el módulo tenía su propio catálogo
(`furniture.product`) con precio, coste y stock copiados de los productos de
Odoo. Eran dos maestros de producto sin relación entre sí: Odoo movía el stock
real y el modelo propio seguía enseñando el número viejo.

Ahora solo existe `product.template`. El módulo le añade los atributos que Odoo
no trae (material, medidas, estilo, garantía) y deja precio, coste,
existencias, categoría y descripción a los campos nativos, que son los que
usan ventas, compras, inventario y la tienda.
"""
from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import ValidationError

GARANTIA_MAXIMA_MESES = 120


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    furniture_material = fields.Char(string='Material')
    furniture_dimensions = fields.Char(
        string='Dimensiones (cm)',
        help='Ancho x fondo x alto, en centímetros.',
    )
    furniture_style = fields.Char(string='Estilo')
    furniture_warranty_months = fields.Integer(string='Garantía (meses)')
    is_furniture = fields.Boolean(
        string='Es mueble del catálogo',
        compute='_compute_is_furniture',
        store=True,
        help='El producto cuelga de la categoría «Muebles de Hogar».',
    )

    @api.depends('categ_id', 'categ_id.parent_path')
    def _compute_is_furniture(self):
        raiz = self.env.ref('ODOO_CRM.categoria_muebles_hogar', raise_if_not_found=False)
        for producto in self:
            producto.is_furniture = bool(
                raiz and producto.categ_id
                and f'/{raiz.id}/' in f'/{producto.categ_id.parent_path or ""}'
            )

    @api.constrains('furniture_warranty_months')
    def _check_furniture_warranty_months(self):
        for producto in self:
            if not 0 <= producto.furniture_warranty_months <= GARANTIA_MAXIMA_MESES:
                raise ValidationError(
                    f'La garantía de «{producto.display_name}» debe estar entre 0 y '
                    f'{GARANTIA_MAXIMA_MESES} meses.'
                )
