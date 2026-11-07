"""Migración 20.0.1.x -> 20.0.2.0.0 (después de cargar el código nuevo).

Copia material, medidas, estilo y garantía desde la copia del catálogo v1
(`furniture_product_v1_backup`) a los productos nativos con el mismo nombre.

- Solo rellena campos vacíos: no pisa lo que alguien haya editado ya en v2.
- El nombre de product.template es traducible (jsonb): se compara con
  cualquiera de sus traducciones.
- Deja en el log cuántas fichas se emparejaron y cuántas no, para conciliar.
"""
import logging

_logger = logging.getLogger(__name__)

BACKUP = 'furniture_product_v1_backup'


def migrate(cr, version):
    if not version:
        return
    cr.execute("SELECT to_regclass(%s) IS NOT NULL", (BACKUP,))
    if not cr.fetchone()[0]:
        return
    cr.execute(f"""
        WITH pareja AS (
            SELECT DISTINCT ON (pt.id) pt.id AS tmpl_id, fp.material, fp.dimensions,
                   fp.style, fp.warranty_months
              FROM product_template pt
              JOIN {BACKUP} fp
                ON EXISTS (SELECT 1 FROM jsonb_each_text(pt.name) t WHERE t.value = fp.name)
             ORDER BY pt.id, fp.id
        )
        UPDATE product_template pt
           SET furniture_material = COALESCE(pt.furniture_material, pareja.material),
               furniture_dimensions = COALESCE(pt.furniture_dimensions, pareja.dimensions),
               furniture_style = COALESCE(pt.furniture_style, pareja.style),
               furniture_warranty_months = COALESCE(NULLIF(pt.furniture_warranty_months, 0),
                                                    pareja.warranty_months)
          FROM pareja
         WHERE pt.id = pareja.tmpl_id
    """)
    actualizados = cr.rowcount
    cr.execute(f"""
        SELECT count(*) FROM {BACKUP} fp
         WHERE NOT EXISTS (
            SELECT 1 FROM product_template pt
             WHERE EXISTS (SELECT 1 FROM jsonb_each_text(pt.name) t WHERE t.value = fp.name))
    """)
    sin_pareja = cr.fetchone()[0]
    _logger.info('ODOO_CRM 2.0: %s productos nativos con ficha de mobiliario; '
                 '%s fichas v1 sin producto con el mismo nombre (siguen en %s)',
                 actualizados, sin_pareja, BACKUP)
