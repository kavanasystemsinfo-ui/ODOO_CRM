# Caso de negocio: de la oportunidad comercial a la entrega

Documento de portfolio. Describe el proceso comercial que el laboratorio
reproduce en Odoo 20 y dice con honestidad qué cubre y qué no. La empresa
(Muebles del Hogar S.L., Castellón) y sus clientes son ficticios; no es una
implantación real.

## La empresa y el problema

Una empresa pequeña de muebles de hogar vende a particulares por la tienda
online y a estudios y proyectos de contract por trato directo. Tiene un
almacén central, cinco proveedores y 80 referencias.

Problemas que el proceso intenta resolver:

1. El comercial no sabe a qué oportunidad llamar primero.
2. Nadie ve de un vistazo qué hay pendiente de entregar o de recibir.
3. Las cifras del día se montan a mano.

## Flujo de punta a punta

| # | Paso | Qué ocurre en Odoo | Quién | Dónde se ve |
|---|---|---|---|---|
| 1 | Entra una oportunidad | Se crea en CRM con cliente, email y las señales comerciales (contract, proyecto referenciado, muestra pedida) | Comercial | Pipeline de CRM |
| 2 | Se puntúa | El módulo calcula un score de 0 a 100 al cambiar cualquier señal y sugiere prioridad | Odoo (automático) | Ficha del lead y panel del día |
| 3 | Se actúa | El comercial sigue la sugerencia, registra correos y actividades; el contacto reciente solo cuenta con correos, mensajes al cliente y actividades hechas | Comercial | Chatter del lead |
| 4 | Presupuesto | Se crea el presupuesto con productos del catálogo nativo | Comercial | Ventas, presupuestos |
| 5 | Pedido | El cliente acepta y el presupuesto se confirma como pedido de venta | Comercial | Ventas, pedidos |
| 6 | Compra | Si falta stock, se pide al proveedor con un pedido de compra | Compras | Compras |
| 7 | Recepción | Llega la mercancía y se valida el albarán de entrada: el stock sube | Almacén | Inventario, recepciones |
| 8 | Entrega | Se prepara y valida el albarán de salida: el stock baja | Almacén | Inventario, entregas |
| 9 | Seguimiento | El panel resume el día con cifras leídas por la API | Dirección | Panel del día |

El paso de factura y cobro **no está modelado de extremo a extremo** (ver
límites). El laboratorio tiene 10 asientos contables, pero no un ciclo de
facturación y cobro completo.

## El score: reglas que se pueden explicar

El score suma pesos fijos por señal activa. No hay modelo de IA:

| Señal | Peso |
|---|---|
| Muestra pedida | 30 |
| Cliente de contract o estudio | 25 |
| Proyecto referenciado | 20 |
| Contacto reciente (últimos 7 días) | 15 |
| Email corporativo | 10 |

Prioridad sugerida: **alta** desde 75, **media** desde 50, **baja** desde 25,
y **ninguna** por debajo. La prioridad solo se sugiere; aplicarla es decisión
del comercial. Para cada combinación hay una plantilla de siguiente acción
(por ejemplo, alta con muestra pedida: coordinar visita física).

Ejemplo: un estudio (25) con proyecto referenciado (20), muestra pedida (30)
y correo corporativo (10) suma 85, prioridad alta. Sin la muestra suma 55,
prioridad media.

## Excepciones y cómo se tratan

| Situación | Tratamiento en el laboratorio |
|---|---|
| Se anota un comentario interno en el lead | No cuenta como contacto: el score no sube |
| Se planifica una actividad pero no se hace | No cuenta como contacto; solo las hechas |
| Cambia una señal | El score y la prioridad se recalculan solos |
| El producto no tiene existencias | El panel muestra recepciones pendientes; la compra la lanza una persona |
| La demo la toca un visitante | Cada 30 minutos se comprueba y se restaura desde una instantánea si cambió |

## Criterios de aceptación

El proceso se da por correcto cuando se cumplen las comprobaciones que ya
ejecuta el CI sobre Odoo 20 real:

- Cambiar una señal recalcula el score (`tests/`, `TransactionCase`).
- Una nota interna no cuenta como contacto real.
- El usuario del panel lee todo lo que necesita y no puede crear, modificar
  ni borrar (el CI intenta escribir con su clave y exige un 403).
- Las cifras del panel coinciden con lo que cuenta el ORM de Odoo.
- Las 80 fichas de la v1 pasan a productos nativos sin duplicados.

## Indicadores

Lo que el panel del día muestra hoy, leído por la API JSON-2:

| Indicador | Valor canónico de la demo |
|---|---|
| Productos publicados | 80 |
| Clientes / proveedores | 34 / 5 |
| Pedidos de venta (confirmados / presupuestos) | 56 (37 / 19) |
| Albaranes (hechos) | 48 (41) |
| Pedidos de compra | 11 |
| Unidades en almacén | 2.190 |
| Actividades | 30 |

Indicadores que un negocio real querría y este laboratorio no calcula:
conversión de oportunidad a pedido, plazo medio de entrega y margen por pedido.

## Qué demuestra y qué no

Demuestra: comprensión del flujo comercial de Odoo, un módulo propio sobre el
modelo nativo, permisos mínimos para una integración, migración de datos entre
versiones y pruebas contra una instancia real.

No demuestra (ver también el README): facturación y cobros, devoluciones,
entregas parciales, la fiscalidad española completa (solo está cargado el IVA
general del 21 %, verificado con una factura de prueba; faltan tipos reducidos,
modelos fiscales y factura electrónica), varios almacenes o empresas, ni la toma de requisitos, formación
y soporte propios de una implantación con usuarios reales.
