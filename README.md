# ODOO_CRM — Laboratorio de empresa ficticia de muebles de hogar

Módulo Odoo que simula una empresa de muebles de hogar: catálogo de 80 productos,
clientes y proveedores del sector, pedidos de venta y compra, almacén con
movimiento trazado, tienda online y panel del día con botón de reinicio.

## Características

- Modelo `furniture.product` con el catálogo de 80 muebles (nombre, categoría,
  PVP, coste, stock, material, dimensiones, estilo, garantía y descripción).
- Categorías: Sofás, Mesas, Sillas, Camas, Armarios, Estanterías, Escritorios,
  Butacas, Mesitas, Recibidores, Bancos y Colchones.
- Los 80 productos del catálogo estándar se extrajeron de District Home (tienda
  online de Green Front Furniture) con `scripts/import_districthome_products.py`,
  y sus imágenes se cargan con `scripts/load_product_images.py`.
- Los tres catálogos (modelo propio, productos estándar y tienda) muestran los
  **mismos 80 productos**: precio, coste, categoría y existencias coinciden.
- Descripciones de venta en español, con material, medidas y estilo deducidos de
  la ficha original.
- **Almacén cuadrado**: las 2.190 unidades en existencias coinciden exactamente
  con la suma de los movimientos de almacén; no hay género sin justificar.
- Almacén vivo: 33 entregas hechas y 4 listas para salir; 8 recepciones hechas y
  3 pendientes de recibir.
- 66 contactos: 34 clientes (estudios de interiorismo, distribuidores y
  *contract*) y 5 proveedores de mobiliario.
- 56 pedidos de venta (37 confirmados y 19 presupuestos) y 11 pedidos de compra.
- 39 oportunidades y 31 actividades, todas en español y del sector.
- Empresa: **Muebles del Hogar S.L.**, con almacén "Almacén central".

## Estructura

- `models/`: modelo `furniture.product`.
- `views/`: vistas del catálogo y plantilla de la página del laboratorio.
- `controllers/`: controlador `/muebles/panel` dentro del sitio web.
- `security/`: permisos de acceso.
- `data/`: catálogo de 80 muebles (`furniture.product.csv`) y datos de origen de
  District Home (`districthome_products.json`).
- `scripts/`: utilidades del laboratorio (ver abajo).
- `panel/`: **panel del día**, su configuración y el motor de restauración.

## Panel del día

- URL pública: `https://muebles.kavanasystems.com/panel/` (servicio propio,
  `muebles-panel.service`, puerto 8081, detrás de nginx).
- Muestra, en lenguaje de negocio: las cifras del día, lo que pide atención
  (actividades vencidas, entregas preparadas, recepciones pendientes) y la salud
  del dato. Entre las comprobaciones de salud va el almacén cuadrado y que todos
  los pedidos apunten al catálogo real.
- Solo lee: consulta el contenedor de PostgreSQL, sin ORM y sin dependencias
  (librería estándar de Python). Si el laboratorio no responde, sirve la caché
  del día y lo declara; no se inventa nada.
- Las frases de resumen son reglas deterministas. La redacción por IA se
  precomputa aparte: sin clave de modelo, el panel lo dice en vez de aparentarlo.
- **Botón de reinicio**: devuelve el laboratorio a su estado inicial desde la
  instantánea canónica. Exige la sesión de administrador del propio Odoo (un
  visitante anónimo recibe un 403) y hay 3 minutos de espera entre reinicios.

```bash
systemctl status muebles-panel                     # estado del servicio
python3 panel/panel_muebles.py --precomputar       # escribe la caché del día
python3 panel/demo_restaurar_muebles.py --estado   # instantánea y recuentos
python3 panel/demo_restaurar_muebles.py --verificar
python3 panel/demo_restaurar_muebles.py --restaurar
```

## Scripts

| Script | Para qué |
| --- | --- |
| `scripts/import_districthome_products.py` | Crea los 80 productos estándar desde el JSON de District Home. |
| `scripts/load_product_images.py` | Descarga y asigna la imagen principal de cada producto. |
| `scripts/create_lab_data.py` | Crea clientes, pedidos y la página del laboratorio. |
| `scripts/limpieza_catalogo.py` | Deja un solo catálogo: renombra socios heredados, reapunta los pedidos al catálogo real y retira el catálogo genérico. |
| `scripts/limpieza_catalogo_remate.py` | Termina la limpieza de las líneas de pedido que Odoo bloqueaba (facturadas/entregadas). |
| `scripts/montar_almacen.py` | Existencias iniciales con movimiento trazado, compras recibidas y entregas hechas. |
| `scripts/retirar_catalogo_heredado.py` | Retira el catálogo genérico que seguía archivado: lotes, facturas de la demo, líneas de pedido y apuntes de valoración. |
| `scripts/arreglar_socios_heredados.py` | Renombra los últimos socios con nombre de la demo y marca clientes y proveedores. |
| `scripts/arreglar_textos_y_hueco.py` | Pasa oportunidades y actividades a español y cuadra el almacén con el libro. |
| `scripts/alinear_modelo.py` | Vuelca el catálogo real en `furniture.product` y regenera el CSV del módulo. |

Se ejecutan con `odoo shell` desde el contenedor:

```bash
docker exec -i <contenedor_odoo> odoo shell -d <base_de_datos> --no-http < scripts/montar_almacen.py
```

## Instalación

1. Clona este repositorio en tu carpeta de addons de Odoo.
2. Actualiza la lista de aplicaciones.
3. Busca "Home Furniture Simulation" e instala.
4. Ejecuta los scripts del laboratorio en este orden: `import_districthome_products.py`,
   `load_product_images.py`, `create_lab_data.py`, `limpieza_catalogo.py`,
   `limpieza_catalogo_remate.py`, `montar_almacen.py`, `retirar_catalogo_heredado.py`,
   `arreglar_socios_heredados.py`, `arreglar_textos_y_hueco.py` y `alinear_modelo.py`.

## Acceso al laboratorio

- URL pública activa: `https://muebles.kavanasystems.com` (HTTPS con Let's Encrypt).
- Landing: `/muebles`. Tienda: `/shop`.
- **Panel del día**: `/panel/`. Panel del módulo (requiere sesión): `/muebles/panel`.
- Acceso local: `http://127.0.0.1:8070`.
- Administrador: usuario `admin`; contraseña en el fichero de credenciales del
  perfil (no versionado).

## Autor

Kavana Systems
