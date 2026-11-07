"""Ficha de mobiliario sobre product.template (hallazgo 2.1 de la auditoría).

Lo que se comprueba es lo que fallaba en la v1: había dos maestros de
producto y el stock del modelo propio no seguía al de Odoo.
"""
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'odoo_crm')
class TestFichaMobiliario(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.raiz = cls.env.ref('ODOO_CRM.categoria_muebles_hogar')
        cls.mesas = cls.env['product.category'].create({
            'name': 'Mesas', 'parent_id': cls.raiz.id,
        })
        cls.mesa = cls.env['product.template'].create({
            'name': 'Mesa de comedor Prueba',
            'categ_id': cls.mesas.id,
            'type': 'consu',
            'is_storable': True,
            'list_price': 450.0,
            'standard_price': 210.0,
            'furniture_material': 'Roble',
            'furniture_dimensions': '180 x 90 x 75',
            'furniture_style': 'Nórdico',
            'furniture_warranty_months': 24,
        })

    def test_no_queda_catalogo_paralelo(self):
        self.assertNotIn('furniture.product', self.env.registry)

    def test_los_atributos_viven_en_el_producto_nativo(self):
        self.assertEqual(self.mesa.furniture_material, 'Roble')
        self.assertEqual(self.mesa.furniture_warranty_months, 24)
        variante = self.mesa.product_variant_id
        self.assertEqual(variante.furniture_style, 'Nórdico')

    def test_es_mueble_si_cuelga_de_la_categoria_raiz(self):
        self.assertTrue(self.mesa.is_furniture)
        otro = self.env['product.template'].create({'name': 'Tornillo suelto'})
        self.assertFalse(otro.is_furniture)
        otro.categ_id = self.mesas
        self.assertTrue(otro.is_furniture)

    def test_las_existencias_son_las_del_almacen_de_odoo(self):
        """Una sola fuente de stock: lo que mueve el almacén es lo que se ve."""
        almacen = self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)
        self.env['stock.quant'].create({
            'product_id': self.mesa.product_variant_id.id,
            'location_id': almacen.lot_stock_id.id,
            'inventory_quantity': 7,
        }).action_apply_inventory()
        self.assertEqual(self.mesa.qty_available, 7)

    def test_garantia_fuera_de_rango(self):
        with self.assertRaises(ValidationError):
            self.mesa.furniture_warranty_months = 500
