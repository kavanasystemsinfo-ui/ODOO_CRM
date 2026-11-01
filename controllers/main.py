from odoo import http
from odoo.http import request
from odoo.http.session import finalize

# Usuario público del laboratorio. Solo este usuario puede abrirse con /demo.
USUARIO_DEMO = 'visita'


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

    @http.route('/demo', type='http', auth='public', website=True, sitemap=False)
    def demo(self, **kwargs):
        """Entrada de un clic al laboratorio: abre la sesión del usuario de visita."""
        if request.session.uid:
            return request.redirect('/odoo')
        usuario = request.env['res.users'].sudo().search(
            [('login', '=', USUARIO_DEMO), ('active', '=', True)], limit=1)
        if not usuario:
            return request.redirect('/web/login')
        sesion = request.session
        sesion['pre_login'] = usuario.login
        sesion['pre_uid'] = usuario.id
        finalize(sesion, request.env(user=None, su=False))
        return request.redirect('/odoo')
