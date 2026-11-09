# Scripts del laboratorio

Qué es cada uno, para no ejecutar por error uno que ya cumplió su función. Todos
los de Odoo se lanzan con `odoo shell -d <base> --no-http < scripts/<nombre>.py`.

## Motor de carga (siembran el laboratorio desde cero)

`import_districthome_products.py`, `load_product_images.py` y
`create_lab_data.py`. El orden completo está en `data/universo.json`.

## Fases históricas (ya aplicadas; no volver a ejecutar sobre la demo)

`limpieza_catalogo.py`, `limpieza_catalogo_remate.py`, `montar_almacen.py`,
`retirar_catalogo_heredado.py`, `arreglar_socios_heredados.py`,
`arreglar_textos_y_hueco.py`, `espanolizar_laboratorio.py`,
`alinear_modelo.py`, `remates_del_sitio.py` y `arreglar_demo_20261107.py`.

Son parches de un solo uso sobre la demo de aquel momento: algunos llevan
identificadores o nombres escritos a mano y escriben con SQL o con `sudo`,
saltándose validaciones del ORM. Sirven como registro de cómo se llegó al estado
actual; la demo se restaura desde la instantánea canónica, no rehaciendo estos
pasos. Una herramienta reutilizable sería una migración del módulo.

## Utilidades

- `anotar_seniales_crm.py`: pone las señales comerciales de las oportunidades.
- `refrescar_cache_web.py`: regenera los bundles web tras restaurar.
- `lint_oca.py`: linter oficial de la OCA sobre el módulo (lo usa el CI).
- `despliegue/`: despliegue de la v2 (ensayado en el CI) y vuelta atrás.
- `systemd/`: servicios y temporizador de la demo.
