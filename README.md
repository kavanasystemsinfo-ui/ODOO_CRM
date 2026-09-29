# ODOO_CRM - Laboratorio de empresa ficticia de muebles de hogar

Módulo Odoo que simula una empresa de muebles de hogar con 80 productos, clientes, pedidos, tienda online y panel de control.

## Características

- Modelo `furniture.product` con catálogo de 80 muebles (nombre, categoría, PVP, coste, stock, material, dimensiones, estilo, garantía y descripción).
- Categorías de producto: Sofás, Mesas, Sillas, Camas, Armarios, Estanterías, Escritorios, Butacas, Mesitas, Recibidores, Bancos y Colchones.
- Productos estándar de Odoo creados a partir del catálogo, publicados en la tienda online.
- Stock inicial para los 80 productos.
- 30 clientes de ejemplo.
- 40 pedidos de venta (la mitad confirmados).
- Landing page en `/muebles`.
- Panel de control en `/muebles/panel` (requiere sesión).
- Tienda online en `/shop`.
- Empresa ficticia: **Muebles del Hogar S.L.**

## Instalación

1. Clona este repositorio en tu carpeta de addons de Odoo.
2. Actualiza la lista de aplicaciones.
3. Busca "Home Furniture Simulation" e instala.
4. Ejecuta el script de datos del laboratorio para crear productos estándar, clientes, pedidos y la página web:

```bash
docker exec -i <contenedor_odoo> odoo shell -d <base_de_datos> --db_host=<host> --db_user=<usuario> --db_password=<contraseña> --no-http < scripts/create_lab_data.py
```

## Estructura

- `models/`: modelo `furniture.product`.
- `views/`: vistas del catálogo y template del panel.
- `controllers/`: controlador del panel `/muebles/panel`.
- `security/`: permisos de acceso.
- `data/`: catálogo de 80 muebles (`furniture.product.csv`).
- `scripts/`: script de creación de datos del laboratorio.

## Acceso al laboratorio

- URL pública prevista: `https://muebles.kavanasystems.com` (pendiente de DNS).
- Acceso local: `http://127.0.0.1:8070`.
- Administrador: usuario `admin`, contraseña `admin` (cambiar en producción).

## Autor

Kavana Systems
