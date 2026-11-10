# ADR-003: la empresa de la demo trabaja sola (simulador por tramos)

- **Estado**: aceptado
- **Fecha**: 2026-11-10

## Contexto

La demo era una foto fija: los últimos pedidos eran de finales de septiembre,
las 30 actividades llevaban semanas vencidas, 33 entregas hechas no tenían
factura, nadie había cobrado nada y ningún producto tenía proveedor. Además,
42 de los 44 leads traían correos de dominios reales, heredados de los datos de
ejemplo de Odoo. El scoring comercial nunca encendía la señal de "contacto
reciente", porque ningún lead tenía mensajes.

## Decisión

Un simulador dentro del módulo (`models/simulador_empresa.py`) hace la jornada
de la empresa por tramos: tres al día de lunes a viernes y uno el sábado.

- **Métodos de negocio de Odoo, no SQL**: `action_confirm`, `button_validate`,
  `_create_invoices`, el asistente de pagos, `button_confirm` de compras... Las
  reglas de cada módulo se aplican igual que si lo hiciera una persona.
- **Coherencia antes que volumen**: solo se confirma lo que tiene stock libre,
  solo se factura lo entregado, solo se cobra lo facturado con tres días de
  margen, y se repone a su proveedor lo que va a agotarse.
- **Reproducible e idempotente**: el plan de cada tramo sale de un aleatorio
  sembrado con su clave (`2026-11-10#13`), y un tramo ya hecho no se repite.
- **Todo o parte, nunca a medias**: cada paso va en su punto de guardado. Si al
  final la base no cuadra (stock negativo, un correo real), se deshace el tramo
  entero.
- **Ningún correo puede salir**: solo dominios reservados (`.example`, RFC
  2606), y los `mail.mail` que deje el tramo se borran sin enviar. El paso de
  correos se repite en cada tramo, así que también limpia lo que escriba un
  visitante.
- **No es una API**: los métodos son privados (JSON-2 no los expone) y exigen
  superusuario.

La orquestación es del servidor (`panel/jornada.sh`, `muebles-jornada.timer`)
y no un `ir.cron`, porque el tramo tiene que ir entre dos operaciones de fuera
de Odoo: restaurar si un visitante tocó la demo, y fijar después la nueva
instantánea con sus recuentos (`<instantánea>.recuentos.json`). La limpieza de
cada media hora compara contra esos recuentos y comparte cerrojo con la
jornada, así que nunca restaura mientras se simula.

## Consecuencias

- Las cifras de la demo cambian cada tramo. Las de `ESPERADO` y las de
  `docs/caso-de-negocio.md` son el estado de publicación, no el de hoy. El de
  hoy lo da el panel.
- La base crece unos pocos pedidos al día: en un año, del orden de un millar.
  No hace falta podarla.
- Si el simulador falla, la jornada no fija instantánea y la demo se queda como
  estaba. El fallo se ve en `journalctl -u muebles-jornada`.
- Pendiente: el visitante sigue entrando a una base compartida. El escaparate de
  solo lectura y las copias por visitante son el paso siguiente.
