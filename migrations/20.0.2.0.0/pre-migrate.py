"""Migración 20.0.1.x -> 20.0.2.0.0 (antes de cargar el código nuevo).

La versión 1 tenía un catálogo paralelo (`furniture.product`). La versión 2 lo
elimina y guarda sus atributos en `product.template`. Antes de que Odoo cargue
el módulo nuevo:

1. La tabla `furniture_product` se RENOMBRA a `furniture_product_v1_backup`.
   Al quitar el modelo, Odoo borraría la tabla al final de la actualización;
   renombrada, se conserva como copia para volver atrás o auditar.
2. Se borran los identificadores externos de esos registros: apuntan a un
   modelo que ya no existe y Odoo intentaría borrarlos uno a uno.
3. Si la base ya tenía una categoría «Muebles de Hogar» creada a mano, se le
   asigna el identificador `ODOO_CRM.categoria_muebles_hogar`, para que el
   fichero de datos no cree una segunda categoría con el mismo nombre.

Es idempotente: se puede ejecutar dos veces sin efecto.
"""
import logging

_logger = logging.getLogger(__name__)

MODULO = 'ODOO_CRM'
BACKUP = 'furniture_product_v1_backup'


def _existe_tabla(cr, tabla):
    cr.execute("SELECT to_regclass(%s) IS NOT NULL", (tabla,))
    return cr.fetchone()[0]


def _tipo_columna(cr, tabla, columna):
    cr.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (tabla, columna),
    )
    fila = cr.fetchone()
    return fila[0] if fila else None


def _respaldar_catalogo(cr):
    if _existe_tabla(cr, 'furniture_product') and not _existe_tabla(cr, BACKUP):
        cr.execute(f'ALTER TABLE furniture_product RENAME TO {BACKUP}')
        cr.execute(f'SELECT count(*) FROM {BACKUP}')
        _logger.info('ODOO_CRM 2.0: furniture_product respaldada en %s (%s filas)',
                     BACKUP, cr.fetchone()[0])
    cr.execute(
        "DELETE FROM ir_model_data WHERE module = %s AND model = 'furniture.product'",
        (MODULO,),
    )


def _vincular_categoria(cr):
    cr.execute(
        "SELECT 1 FROM ir_model_data WHERE module = %s AND name = 'categoria_muebles_hogar'",
        (MODULO,),
    )
    if cr.fetchone() or not _existe_tabla(cr, 'product_category'):
        return
    # name es texto plano en product.category, pero se contempla jsonb por si
    # una versión futura lo hace traducible.
    if _tipo_columna(cr, 'product_category', 'name') == 'jsonb':
        condicion = "EXISTS (SELECT 1 FROM jsonb_each_text(name) t WHERE t.value = %s)"
    else:
        condicion = "name = %s"
    cr.execute(
        f"SELECT id FROM product_category WHERE parent_id IS NULL AND {condicion} "
        "ORDER BY id LIMIT 1",
        ('Muebles de Hogar',),
    )
    fila = cr.fetchone()
    if not fila:
        return
    cr.execute(
        "INSERT INTO ir_model_data (module, name, model, res_id, noupdate) "
        "VALUES (%s, 'categoria_muebles_hogar', 'product.category', %s, true)",
        (MODULO, fila[0]),
    )
    _logger.info('ODOO_CRM 2.0: categoría existente %s vinculada a categoria_muebles_hogar',
                 fila[0])


def migrate(cr, version):
    if not version:
        return  # instalación nueva: no hay nada que migrar
    _respaldar_catalogo(cr)
    _vincular_categoria(cr)
