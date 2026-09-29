# ODOO_CRM - Laboratorio de empresa ficticia de muebles de hogar

Módulo Odoo que simula una empresa de muebles de hogar: catálogo de 80 productos,
clientes y proveedores del sector, pedidos de venta y compra, almacén con
movimiento real, tienda online y panel de control.

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
- Descripciones de venta en español y material, medidas y estilo deducidos de la
  ficha original.
- Almacén coherente: existencias iniciales con movimiento trazado, 33 entregas
  hechas y 4 listas para salir, 8 recepciones hechas y 3 pendientes.
- 66 contactos: clientes (estudios de interiorismo, distribuidores y contract) y
  proveedores de mobiliario.
- 56 pedidos de venta: 37 confirmados y 19 presupuestos.
- 11 pedidos de compra a proveedores de mobiliario.
- Empresa: **Muebles del Hogar S.L.**, con almacén "Almacén central".

## Estructura

- `models/`: modelo `furniture.product`.
- `views/`: vistas del catálogo y template del panel.
- `controllers/`: controlador del panel `/muebles/panel`.
- `security/`: permisos de acceso.
- `data/`: catálogo de 80 muebles (`furniture.product.csv`) y datos de origen
  de District Home (`districthome_products.json`).
- `scripts/`: utilidades del laboratorio (ver abajo).

## Scripts

| Script | Para qué |
| --- | --- |
| `scripts/import_districthome_products.py` | Crea los 80 productos estándar desde el JSON de District Home. |
| `scripts/load_product_images.py` | Descarga y asigna la imagen principal de cada producto. |
| `scripts/create_lab_data.py` | Crea clientes, pedidos y la página del laboratorio. |
| `scripts/limpieza_catalogo.py` | Deja un solo catálogo: renombra socios heredados, reapunta los pedidos al catálogo real y retira el catálogo genérico. |
| `scripts/limpieza_catalogo_remate.py` | Termina la limpieza de las líneas de pedido que Odoo bloqueaba (facturadas/entregadas). |
| `scripts/montar_almacen.py` | Existencias iniciales con movimiento trazado, compras recibidas y entregas hechas. |
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
   `montar_almacen.py` y `alinear_modelo.py`.

## Acceso al laboratorio

- URL pública activa: `https://muebles.kavanasystems.com` (HTTPS con Let's Encrypt).
- Landing: `/muebles`. Tienda: `/shop`. Panel: `/muebles/panel` (requiere sesión).
- Acceso local: `http://127.0.0.1:8070`.
- Administrador: usuario `admin`; contraseña en el fichero de credenciales del
  perfil (no versionado).

## Autor

Kavana Systems
