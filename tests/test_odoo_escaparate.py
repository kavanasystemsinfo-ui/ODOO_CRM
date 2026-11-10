"""Escaparate de solo lectura: el visitante ve toda la empresa y no cambia nada."""
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

GRUPOS_VISITA = ('base.group_user,sales_team.group_sale_salesman_all_leads,'
                 'purchase.group_purchase_user,stock.group_stock_manager,'
                 'account.group_account_readonly')


@tagged('post_install', '-at_install', 'odoo_crm')
class TestEscaparate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.visita = new_test_user(cls.env, login='visita_escaparate',
                                   groups=GRUPOS_VISITA + ',ODOO_CRM.group_escaparate')
        cls.comercial = new_test_user(cls.env, login='comercial_escaparate', groups=GRUPOS_VISITA)
        cls.cliente = cls.env['res.partner'].create({'name': 'Hotel Morella'})
        cls.lead = cls.env['crm.lead'].create({'name': 'Sillas para la terraza',
                                               'partner_id': cls.cliente.id})
        cls.producto = cls.env['product.product'].create({'name': 'Silla Turia', 'list_price': 90})
        cls.pedido = cls.env['sale.order'].create({
            'partner_id': cls.cliente.id,
            'order_line': [(0, 0, {'product_id': cls.producto.id, 'product_uom_qty': 2})],
        })

    def _como(self, registro, usuario=None):
        return registro.with_user(usuario or self.visita)

    def test_lee_toda_la_empresa(self):
        for modelo in ('crm.lead', 'sale.order', 'res.partner', 'product.template',
                       'stock.picking', 'purchase.order', 'account.move', 'mail.message'):
            with self.subTest(modelo=modelo):
                self.env[modelo].with_user(self.visita).search_read([], limit=3)
        self.assertEqual(self._como(self.lead).name, 'Sillas para la terraza')

    def test_no_crea_modifica_ni_borra(self):
        casos = [(self.lead, {'name': 'Cambiado'}), (self.pedido, {'note': 'Cambiado'}),
                 (self.cliente, {'name': 'Cambiado'}),
                 (self.producto.product_tmpl_id, {'name': 'Cambiado'})]
        for registro, valores in casos:
            visto = self._como(registro)
            with self.subTest(modelo=registro._name):
                for operacion in ('create', 'write', 'unlink'):
                    self.assertFalse(visto.has_access(operacion), operacion)
                with self.assertRaisesRegex(AccessError, 'solo lectura'):
                    visto.write(valores)
                with self.assertRaises(AccessError):
                    visto.unlink()
                with self.assertRaises(AccessError):
                    visto.browse().create(valores)

    def test_no_escribe_en_el_chatter_ni_confirma(self):
        with self.assertRaises(AccessError):
            self._como(self.lead).message_post(body='Hola', message_type='comment',
                                               subtype_xmlid='mail.mt_comment')
        with self.assertRaises(AccessError):
            self._como(self.lead).activity_schedule('mail.mail_activity_data_call')
        with self.assertRaises(AccessError):
            self._como(self.pedido).action_confirm()
        self.assertEqual(self.pedido.state, 'draft')

    def test_los_demas_usuarios_no_cambian(self):
        self._como(self.lead, self.comercial).write({'name': 'Lo cambia el comercial'})
        self.assertEqual(self.lead.name, 'Lo cambia el comercial')

    def test_navegar_no_falla_por_preferencias(self):
        ajustes = self.env['res.users.settings'].with_user(self.visita)
        ajustes._find_or_create_for_user(self.visita)

    def test_recorre_todos_los_menus_como_visitante(self):
        """Cada menú con acción de ventana: vistas y lista se cargan sin error."""
        menus = self.env['ir.ui.menu'].with_user(self.visita).search([('action', '!=', False)])
        errores, recorridos = [], 0
        for menu in menus:
            accion = menu.sudo().action
            if not accion or accion._name != 'ir.actions.act_window' or not accion.res_model:
                continue
            Modelo = self.env[accion.res_model].with_user(self.visita)
            if not Modelo.has_access('read'):
                continue
            try:
                Modelo.get_views([(False, 'list'), (False, 'form')])
                Modelo.search_read([], limit=3)
                recorridos += 1
            except Exception as exc:  # noqa: BLE001 - se acumulan para verlos todos
                errores.append(f'{menu.complete_name} ({accion.res_model}): {exc}')
        self.assertEqual(errores, [])
        self.assertGreater(recorridos, 20)

    def test_preparar_visita_pone_el_grupo(self):
        visita = new_test_user(self.env, login='visita', groups='base.group_user')
        self.env['odoo_crm.escaparate']._preparar_visita()
        self.assertTrue(visita.has_group('ODOO_CRM.group_escaparate'))
        self.assertTrue(visita.has_group('account.group_account_readonly'))
