from odoo import models, fields


class FurnitureProduct(models.Model):
    _name = 'furniture.product'
    _description = 'Producto de muebles de hogar'
    _order = 'name'

    name = fields.Char(string='Nombre', required=True)
    category = fields.Selection([
        ('sofas', 'Sofás'),
        ('mesas', 'Mesas'),
        ('sillas', 'Sillas'),
        ('camas', 'Camas'),
        ('armarios', 'Armarios'),
        ('estanterias', 'Estanterías'),
        ('escritorios', 'Escritorios'),
        ('butacas', 'Butacas'),
        ('mesitas', 'Mesitas'),
        ('recibidores', 'Recibidores'),
        ('bancos', 'Bancos'),
        ('colchones', 'Colchones'),
        ('otros', 'Otros'),
    ], string='Categoría', required=True)
    list_price = fields.Float(string='PVP (€)')
    standard_price = fields.Float(string='Coste (€)')
    qty_available = fields.Integer(string='Stock')
    material = fields.Char(string='Material')
    dimensions = fields.Char(string='Dimensiones (cm)')
    style = fields.Char(string='Estilo')
    warranty_months = fields.Integer(string='Garantía (meses)')
    description = fields.Text(string='Descripción')
    active = fields.Boolean(string='Activo', default=True)
