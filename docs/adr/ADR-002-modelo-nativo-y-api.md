# ADR-002: modelo nativo, API JSON-2 y migración de datos (v2 del módulo)

- **Estado**: aceptado
- **Fecha**: 2026-11-07
- **Sustituye a**: ADR-001 (migración a Odoo 18; el laboratorio ya corre Odoo 20)
- **Origen**: auditoría externa del repositorio (07-11-2026), verificada punto
  por punto contra el código antes de cambiar nada

## Contexto

La auditoría señaló, y la revisión del código confirmó, cinco problemas de la v1:

1. **Dos maestros de producto.** `furniture.product` copiaba nombre, precio,
   coste y stock de `product.template` sin relación entre ambos. Odoo movía el
   stock real y el modelo propio seguía enseñando el valor sembrado.
2. **El panel leía PostgreSQL directamente**: 35 consultas SQL, usuario y
   contraseña fijos en el código, escuchando en `0.0.0.0`. El cliente JSON-RPC
   existía pero nadie lo llamaba, y README y SECURITY decían lo contrario.
3. **Campos calculados sin `@api.depends`**: al marcar una señal en una
   oportunidad, el score no se recalculaba en la misma transacción.
4. **"Contacto reciente" medía fechas límite**: una llamada planificada para
   mañana contaba como contacto hecho.
5. **No había pruebas sobre un Odoo real**: solo pruebas que leían el texto del
   código. Nadie había comprobado que el módulo se instalara en una base vacía.

Al montar esas pruebas aparecieron tres más que la auditoría no vio:

6. `docker-compose.yml` traía PostgreSQL 15 y **Odoo 20 necesita 16 o superior**
   (usa `any_value()`): un laboratorio nuevo no llegaba a crear la base.
7. En Odoo 20 la API JSON-2 **solo acepta claves con alcance `rpc`** y las claves
   de usuarios no administradores caducan en 1 día salvo que su grupo diga otra
   cosa.
8. El README publicaba la contraseña del usuario de visita de la demo.

## Decisión

### Producto: ampliar, no duplicar

Los atributos que Odoo no trae (material, medidas, estilo, garantía) se añaden a
`product.template` con `_inherit`. Precio, coste, existencias, categoría y
descripción son los nativos, que son los que usan ventas, compras, inventario y
tienda. `is_furniture` (calculado y guardado, depende de `categ_id.parent_path`)
marca lo que cuelga de la categoría raíz «Muebles de Hogar», que ahora tiene
identificador externo en el módulo.

Un modelo separado tendría sentido si el mueble fuera otra cosa que un producto
(por ejemplo, una configuración a medida con su propio ciclo de vida). Aquí no
lo es.

### Migración de datos: sin pérdida y reversible

`migrations/20.0.2.0.0/`:

- `pre-migrate`: **renombra** la tabla `furniture_product` a
  `furniture_product_v1_backup` (Odoo la borraría al retirar el modelo), borra
  los identificadores externos que apuntaban a ese modelo y, si la base ya
  tenía una «Muebles de Hogar» creada a mano, le asigna el identificador del
  módulo para no crear otra.
- `post-migrate`: copia los atributos a los productos nativos emparejando por
  nombre (el nombre de `product.template` es traducible: se compara con
  cualquiera de sus traducciones), **sin pisar** campos ya rellenos, y deja en
  el log cuántas fichas se emparejaron y cuántas no.

Volver atrás es posible: la copia de la tabla sigue en la base.

### Panel: API JSON-2 con un usuario de solo lectura

El panel lee con `POST /json/2/<modelo>/<método>` y una API key, con la
librería estándar (sin `odoorpc` ni `psycopg2`). Motivos:

- es la API externa que Odoo recomienda desde la 19 (XML-RPC y JSON-RPC
  clásicos están en retirada);
- respeta permisos, reglas de registro y campos calculados: el score de la
  oportunidad lo calcula el módulo y el panel solo lo lee, en vez de repetir la
  fórmula con SQL;
- la clave es de un usuario técnico con el grupo «Panel del día: solo lectura»,
  caduca como mucho a los 90 días y se puede revocar sin tocar a nadie más.

Las cifras conservan los estados y umbrales que publicaba la versión SQL. Donde
SQL contaba registros que el ORM no considera vigentes (archivados, líneas de
sección sin producto) se sigue al ORM.

### Pruebas: sobre Odoo 20 de verdad

El workflow `odoo` instala el módulo en una base vacía con la imagen oficial y
ejecuta las pruebas `TransactionCase`; prueba el panel de extremo a extremo
contra ese Odoo (incluida la negativa a escribir) y ensaya la actualización
desde el último commit de la v1. Las pruebas de los defectos 1, 3 y 4 fallan con
el código de la v1 y pasan con el de la v2.

## Consecuencias

- **Desplegar en la demo pública no es un `git pull`**: hay que actualizar el
  módulo (`-u ODOO_CRM`), crear el usuario de integración y su clave, poner la
  clave en el entorno del panel y **regenerar la instantánea canónica** de la
  restauración (la actual es de la v1 y restaurarla deshace la migración).
  Antes conviene pasar la base de PostgreSQL 15 a 17 con copia de seguridad.
- Los scripts de poblado escriben ahora la ficha en `product.template` y leen
  el catálogo de `data/catalogo_muebles.csv`, que Odoo no carga.
- Queda como deuda renombrar los campos `x_` del CRM (prefijo reservado a
  campos creados desde la interfaz); es una migración de columnas aparte.
