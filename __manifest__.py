{
    'name': 'Mobiliario del Hogar (laboratorio ODOO_CRM)',
    'version': '20.0.2.0.0',
    'category': 'Sales',
    'summary': 'Empresa ficticia de muebles sobre Odoo 20: ficha de mobiliario, '
               'scoring comercial y usuario de integración de solo lectura',
    'description': """
Laboratorio de una empresa de muebles de hogar sobre Odoo 20.

* Amplía el producto nativo (product.template) con material, medidas, estilo y
  garantía. No hay catálogo paralelo: precio, coste y existencias son los de Odoo.
* Hereda crm.lead con cinco señales comerciales y un score determinista.
* Define el grupo «Panel del día: solo lectura» para el usuario de integración
  que usa el panel externo por JSON-RPC.
    """,
    'author': 'Kavana Systems',
    'website': 'https://github.com/kavanasystemsinfo-ui/ODOO_CRM',
    'depends': [
        'base', 'mail', 'product', 'stock', 'account', 'sale_management',
        'purchase', 'crm', 'contacts', 'website', 'website_sale',
    ],
    'data': [
        'security/groups.xml',
        'security/ir.access.csv',
        'security/panel_reglas.xml',
        'data/product_category.xml',
        'data/escaparate.xml',
        'views/product_template_views.xml',
        'views/crm_lead_scoring_views.xml',
        'views/panel_template.xml',
    ],
    # Catálogo de referencia que siembra scripts/create_lab_data.py; Odoo no lo
    # carga (convención del linter OCA para ficheros cargados a mano).
    'oca_data_manual': ['data/catalogo_muebles.csv'],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
