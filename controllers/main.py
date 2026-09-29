from odoo import http
from odoo.http import request


class FurnitureLabController(http.Controller):

    @http.route('/muebles/panel', type='http', auth='user', website=True)
    def panel(self, **kwargs):
        env = request.env
        total_products = env['product.template'].search_count([])
        furniture_products = env['product.template'].search_count([
            ('categ_id.parent_id.name', '=', 'Muebles de Hogar')
        ])
        customers = env['res.partner'].search_count([('customer_rank', '>', 0)])
        orders = env['sale.order'].search_count([])
        values = {
            'total_products': total_products,
            'furniture_products': furniture_products,
            'customers': customers,
            'orders': orders,
        }
        return request.render('ODOO_CRM.panel_template', values)
