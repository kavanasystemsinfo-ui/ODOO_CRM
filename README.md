# ODOO_CRM — Laboratorio de empresa ficticia de muebles de hogar

Módulo Odoo que simula una **empresa española** de muebles de hogar: catálogo de
80 productos, clientes y proveedores del sector, pedidos de venta y compra,
almacén con movimiento trazado, tienda online y panel del día con botón de
reinicio.

## Características

- Modelo `furniture.product` con el catálogo de 80 muebles (nombre, categoría,
  PVP, coste, stock, material, dimensiones, estilo, garantía y descripción).
- Los 80 productos del catálogo estándar se extrajeron de District Home (tienda
  online de Green Front Furniture) con `scripts/import_districthome_products.py`,
  y sus imágenes se cargan con `scripts/load_product_images.py`. El origen de los
  datos es estadounidense, pero **el laboratorio está ambientado como empresa
  española**: nombres de producto, categorías, descripciones, moneda e impuestos
  en español.
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
- 39 oportunidades y 30 actividades, todas en español y del sector.
- Empresa: **Muebles del Hogar S.L.**, Castelló de la Plana, con almacén
  "Almacén central".

## Ambiente español

- **Idioma**: español (`es_ES`) cargado y por defecto en usuarios, socios y web.
  La web sirve solo en español y el backend se ve en español (los tramos del CRM
  son Nuevo, Calificado, Propuesta y Ganado).
- **Moneda**: euro. El dólar queda desactivado y los importes se muestran en
  formato español (12.415,50 €).
- **Impuestos**: IVA 21 % en venta y en compra, aplicado a productos, pedidos y
  facturas. Las facturas heredadas de la demo —que citaban referencias
  inexistentes y seguían al 15 %— se retiraron; quedan 10 asientos de banco y
  varios, sin IVA.
- **Tienda**: árbol de categorías propio (Sofás y chaise longue, Mesas de
  comedor, Mesitas y mesas de centro, Sillas y taburetes, Sillones y butacas,
  Bancos y pufs, Armarios y vitrinas, Dormitorio, Recibidores y consolas y
  Decoración y espejos) en lugar de las categorías de la demo de Odoo.
- **NIF**: el del laboratorio es ficticio (B12345678); se cambia en un minuto.

Aviso para quien repita esto: cambiar el idioma o la moneda **por SQL desde
fuera** no invalida la caché del servidor en marcha, y la web puede quedarse
dando error 500 aunque los datos ya sean correctos. Ver
`scripts/refrescar_cache_web.py` y la cabecera de
`scripts/espanolizar_laboratorio.py`.

## Estructura

- `models/`: modelo `furniture.product`.
- `views/`: vistas del catálogo y plantilla de la página del laboratorio.
- `controllers/`: controlador `/muebles/panel` dentro del sitio web.
- `security/`: permisos de acceso.
- `data/`: catálogo de 80 muebles (`furniture.product.csv`) y datos de origen de
  District Home (`districthome_products.json`).
- `scripts/`: utilidades del laboratorio (ver abajo).
- `panel/`: **panel del día**, su configuración y el motor de restauración.

## Landing del proyecto

- URL pública: `https://muebles.kavanasystems.com/muebles/` (y el dominio raíz
  redirige ahí). Es la puerta de entrada que ve quien visita el proyecto.
- Es una página **estática** (`/var/www/html/muebles/`, versionada en
  `landing/`), con el estilo de Kavana Systems: tema oscuro, naranja corporativo,
  tipografías Inter y JetBrains Mono.
- Cuenta qué es el laboratorio, cómo está montado, qué hay dentro con su estado
  (VERIFICADO), cómo funciona el panel del día, las capturas reales y el acceso
  a la demostración. **Toda cifra de la landing se puede comprobar en el
  laboratorio en marcha.**
- Al publicarla, la portada del sitio de Odoo pasó a ser la tienda (`/shop`) y
  la antigua página del laboratorio se movió a `/laboratorio`. El panel del
  módulo sigue en `/muebles/panel` (lo sirve Odoo, no la landing).

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
| `scripts/espanolizar_laboratorio.py` | Pasa el laboratorio a empresa española: idioma y traducciones, moneda única euro, IVA 21 %, país y NIF, los 80 nombres de mueble, el árbol de la tienda y las facturas de la demo. |
| `scripts/refrescar_cache_web.py` | Refresca la caché del Odoo en marcha escribiendo por XML-RPC (necesario tras cambios hechos por SQL desde fuera). |
| `scripts/alinear_modelo.py` | Vuelca el catálogo real en `furniture.product` y regenera el CSV del módulo. |

Se ejecutan con `odoo shell` desde el contenedor:

```bash
docker exec -i <contenedor_odoo> odoo shell -d <base_de_datos> --no-http < scripts/montar_almacen.py
```

## Instalación

1. Clona este repositorio en tu carpeta de addons de Odoo.
2. Actualiza la lista de aplicaciones.
3. Busca "Mobiliario del Hogar" e instala.
4. Ejecuta los scripts del laboratorio en el orden de la tabla anterior:
   `import_districthome_products.py`, `load_product_images.py`,
   `create_lab_data.py`, `limpieza_catalogo.py`, `limpieza_catalogo_remate.py`,
   `montar_almacen.py`, `retirar_catalogo_heredado.py`,
   `arreglar_socios_heredados.py`, `arreglar_textos_y_hueco.py`,
   `espanolizar_laboratorio.py` y `alinear_modelo.py`.

## Acceso al laboratorio

- URL pública activa: `https://muebles.kavanasystems.com` (HTTPS con Let's Encrypt).
- Landing: `/muebles`. Tienda: `/shop`.
- **Panel del día**: `/panel/`. Panel del módulo (requiere sesión): `/muebles/panel`.
- Acceso local: `http://127.0.0.1:8070`.
- Administrador: usuario `admin`; contraseña en el fichero de credenciales del
  perfil (no versionado).

## Autor

Kavana Systems
