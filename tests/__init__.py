# Pruebas que ejecuta Odoo (--test-tags /ODOO_CRM) sobre una base limpia.
# La suite de pytest de esta carpeta no necesita Odoo; por eso la importación
# se protege: sin Odoo instalado (CI estático, portátil) no se carga nada.
try:
    import odoo  # noqa: F401
except ImportError:  # pragma: no cover - entorno sin Odoo
    pass
else:
    from . import test_odoo_producto
    from . import test_odoo_scoring
    from . import test_odoo_permisos_panel
    from . import test_odoo_simulador
