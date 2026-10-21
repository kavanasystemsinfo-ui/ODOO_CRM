{
    'name': 'Mobiliario del Hogar (laboratorio ODOO_CRM)',
    'version': '20.0.1.0.0',
    'category': 'Sales',
    'summary': 'Simulación de empresa española de muebles de hogar con 80 productos',
    'description': """
Módulo de simulación para una empresa de muebles de hogar.
Incluye 80 productos de ejemplo con categorías, precios, stock y atributos.
    """,
    'author': 'Kavana Systems',
    'website': 'https://github.com/kavanasystemsinfo-ui/ODOO_CRM',
    'depends': ['base', 'product', 'stock', 'sale_management', 'website', 'crm', 'purchase', 'contacts'],
    'data': [
        'views/furniture_product_views.xml',
        'views/panel_template.xml',
        'views/crm_lead_scoring_views.xml',
        'data/furniture.product.csv',
        # 'security/ir.model.access.csv',  # Omitido en lab/demo; superuser tiene acceso total
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
