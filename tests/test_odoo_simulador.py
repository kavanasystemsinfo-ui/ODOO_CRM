"""Simulador de la empresa viva: una quincena de trabajo debe dejar la base coherente."""
from datetime import date, datetime, timedelta

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models import simulador_plan as plan


@tagged('post_install', '-at_install', 'odoo_crm')
class TestSimulador(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Sim = cls.env['odoo_crm.simulador'].sudo()
        cls.env['res.partner'].create({'name': 'Maderas Turia S.L.', 'is_company': True,
                                       'supplier_rank': 1, 'email': 'info@maderasturia.example'})
        cliente = cls.env['res.partner'].create({
            'name': 'Hotel Morella', 'is_company': True, 'email': 'compras@hotelmorella.example'})
        almacen = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)],
                                                    limit=1)
        cls.productos = cls.env['product.product']
        for i in range(6):
            producto = cls.env['product.product'].create({
                'name': f'Silla de prueba {i}', 'type': 'consu', 'is_storable': True,
                'list_price': 120 + i, 'standard_price': 60 + i,
            })
            cls.env['stock.quant']._update_available_quantity(
                producto, almacen.lot_stock_id, 6 + i)
            cls.productos |= producto
        pedido = cls.env['sale.order'].create({
            'partner_id': cliente.id,
            'order_line': [(0, 0, {'product_id': cls.productos[0].id, 'product_uom_qty': 1})],
        })
        pedido.action_confirm()
        # Entrega heredada: hecha, pero vinculada al pedido solo por el texto «origen».
        heredado = cls.env['sale.order'].create({
            'partner_id': cliente.id,
            'order_line': [(0, 0, {'product_id': cls.productos[1].id, 'product_uom_qty': 2})],
        })
        heredado.action_confirm()
        albaran = heredado.picking_ids
        albaran.move_ids.sale_line_id = False
        albaran.sale_id = False
        albaran.origin = heredado.name
        albaran.move_ids.quantity = 2
        albaran.move_ids.picked = True
        albaran.button_validate()
        # Como en la demo: la salida hecha acabó en la vista del almacén, no en Clientes.
        vista = almacen.view_location_id.id
        cls.env.flush_all()
        cls.env.cr.execute('UPDATE stock_move SET location_dest_id = %s WHERE picking_id = %s',
                           (vista, albaran.id))
        cls.env.cr.execute('UPDATE stock_move_line SET location_dest_id = %s WHERE picking_id = %s',
                           (vista, albaran.id))
        cls.env.invalidate_all()
        cls.pedido_heredado = heredado
        # Restos de los datos de ejemplo: proveedor en California, lead con teléfono
        # belga y la empresa en el título, línea de pedido en inglés.
        cls.proveedor_us = cls.env['res.partner'].create({
            'name': 'Fusteria Industrial Turia S.L.', 'is_company': True, 'supplier_rank': 1,
            'street': '1839 Arbor Way', 'city': 'Turlock', 'zip': '95380',
            'country_id': cls.env.ref('base.us').id, 'vat': 'US12345672',
            'phone': '(623)-853-7197'})
        cls.lead_demo = cls.env['crm.lead'].create({
            'name': 'Presupuesto de 25 mesas de comedor — Contract Habitat',
            'phone': '+32 10 588 558', 'type': 'lead'})
        cls.linea_ingles = pedido.order_line[0]
        cls.linea_ingles.name = 'Tufted Gallery Bench\nAdd a touch of sophistication with the bench'
        cls.lead_real = cls.env['crm.lead'].create({
            'name': 'Lead con correo de un dominio real', 'email_from': 'compras@reuters.com'})
        cls.nota_real = cls.lead_real.message_post(
            body='Escribir a ErikNFrench@armyspy.com o a info@hotelmorella.example',
            message_type='comment', subtype_xmlid='mail.mt_note')

    def _tramos(self, desde: date, dias: int):
        for d in range(dias):
            dia = desde + timedelta(days=d)
            for hora in plan.TRAMOS[dia.weekday()]:
                yield datetime(dia.year, dia.month, dia.day, hora, 5)

    def test_solo_lo_lanza_el_sistema(self):
        usuario = new_test_user(self.env, login='comercial_sim', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['odoo_crm.simulador'].with_user(usuario)._simular_tramo(
                datetime(2026, 11, 9, 9, 5))

    def test_un_tramo_no_se_repite_y_el_domingo_no_se_trabaja(self):
        primero = self.Sim._simular_tramo(datetime(2026, 11, 9, 9, 5))
        self.assertEqual(primero['tramo'], '2026-11-09#09')
        self.assertIn('omitido', self.Sim._simular_tramo(datetime(2026, 11, 9, 9, 40)))
        self.assertIn('omitido', self.Sim._simular_tramo(datetime(2026, 11, 15, 12, 0)))

    def test_vincula_la_entrega_heredada_y_se_factura(self):
        self.assertEqual(self.pedido_heredado.order_line.qty_delivered, 0)
        self.Sim._simular_tramo(datetime(2026, 11, 9, 9, 5))
        self.assertEqual(self.pedido_heredado.order_line.qty_delivered, 2)
        if self.env['account.journal'].search([('type', '=', 'sale')], limit=1):
            for momento in self._tramos(date(2026, 11, 9), 3):
                self.Sim._simular_tramo(momento)
            self.assertTrue(self.pedido_heredado.invoice_ids)

    def test_una_quincena_de_trabajo_coherente(self):
        totales, incidencias = {}, []
        for momento in self._tramos(date(2026, 11, 9), 14):
            resumen = self.Sim._simular_tramo(momento)
            self.assertNotIn('omitido', resumen, momento)
            incidencias += resumen['incidencias']
            for clave, valor in resumen.items():
                if isinstance(valor, int):
                    totales[clave] = totales.get(clave, 0) + valor
        self.assertEqual(incidencias, [], totales)
        for clave in ('leads_nuevos', 'cualificaciones', 'propuestas', 'correos_cliente',
                      'confirmaciones', 'entregas', 'compras'):
            with self.subTest(clave=clave):
                self.assertGreater(totales.get(clave, 0), 0, totales)
        if self.env['account.journal'].search([('type', '=', 'sale')], limit=1):
            self.assertGreater(totales.get('facturas', 0), 0, totales)

        self.assertFalse(self.env['stock.quant'].search_count(
            [('location_id.usage', '=', 'internal'), ('quantity', '<', 0)]))
        self.assertTrue(plan.es_email_ficticio(self.lead_real.email_from))
        self.assertNotIn('armyspy', str(self.nota_real.body))
        self.assertIn('info@hotelmorella.example', str(self.nota_real.body))
        self.assertFalse(self.env['mail.mail'].search_count([('state', '=', 'outgoing')]))
        # Lo facturado salió del almacén: ningún pedido facturado sin entrega hecha.
        facturados = self.env['sale.order'].search([('invoice_ids', '!=', False)])
        for pedido in facturados:
            self.assertTrue(all(p.state in ('done', 'cancel') for p in pedido.picking_ids),
                            pedido.name)
        # La señal de contacto se alimenta: hay oportunidades con contacto reciente.
        ganadas_o_vivas = self.env['crm.lead'].search([('type', '=', 'opportunity')])
        self.assertTrue(any(lead.x_fecha_ultimo_contacto for lead in ganadas_o_vivas))

    def test_los_datos_quedan_coherentes(self):
        resumen = self.Sim._simular_tramo(datetime(2026, 11, 9, 9, 5))
        self.assertEqual(resumen['incidencias'], [])
        proveedor = self.proveedor_us
        self.assertEqual(proveedor.country_id.code, 'ES')
        self.assertEqual(proveedor.city, 'València')       # «Turia» -> València
        self.assertTrue(proveedor.zip.startswith('460'))
        self.assertEqual(proveedor.state_id.code, 'V')
        self.assertTrue(proveedor.phone.startswith('+34 96'))
        self.assertRegex(proveedor.vat, r'^ESB\d{8}$')
        lead = self.lead_demo
        self.assertEqual(lead.partner_name, 'Contract Habitat')
        self.assertTrue(lead.contact_name and lead.contact_name != lead.name)
        self.assertTrue(lead.phone.startswith('+34 6'))
        self.assertEqual(lead.country_id.code, 'ES')
        self.assertNotIn('Tufted', self.linea_ingles.name)
        self.assertTrue(self.env['ir.config_parameter'].sudo().get_str('web.base.url').startswith('https://'))
        # Una segunda pasada no cambia nada (idempotente).
        self.assertEqual(self.Sim._coherencia_datos(), 0)
