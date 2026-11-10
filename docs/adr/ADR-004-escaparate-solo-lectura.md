# ADR-004: escaparate de solo lectura para la demo pública

- **Estado**: aceptado
- **Fecha**: 2026-11-10

## Contexto

Con la empresa simulada (ADR-003), la base de la demo tiene historia real y
crece cada tramo. El visitante entraba como usuario interno con permisos de
ventas, compras e inventario: podía cambiar o borrar lo que veía el siguiente.
La limpieza de cada media hora lo arreglaba después, pero no lo evitaba.

## Opciones

1. **Restricciones `ir.access` modelo a modelo** (lo que ya hace el grupo del
   panel). Son explícitas, pero la demo tiene más de cien modelos navegables y
   cada módulo nuevo añade más. Un olvido es un agujero.
2. **Un único cierre en el punto por el que pasan todos los permisos.** En
   Odoo 20, ACL y reglas se resuelven en `Model._access_domain(operación)`. Si
   para el grupo del escaparate ese dominio es falso en create/write/unlink,
   Odoo lo trata como permiso inexistente en `has_access`, `check_access` y la
   interfaz.
3. **Copia de la base por visitante.** Es lo que permitiría "probar" con
   libertad, pero el VPS de 4 GB solo admite unas 3 copias a la vez, y la
   decisión es no gastar más en él.

## Decisión

La opción 2, con dos excepciones acotadas:
- los modelos transitorios (asistentes), porque lo que intenten escribir en un
  modelo real vuelve a estar cerrado;
- las preferencias y la presencia de la sesión (`EXCEPCIONES`).

El código que Odoo ejecuta como superusuario no pasa por el cierre, y por eso el
simulador sigue trabajando.

## Verificación

- Tests de Odoo: el visitante lee todos los módulos y no puede crear, modificar
  ni borrar, ni publicar en el chatter, ni planificar actividades ni confirmar
  pedidos. Un usuario sin el grupo sigue escribiendo, y se recorren todos los
  menús como visitante.
- Ensayo sobre una copia de producción con el usuario `visita` real: 184 menús
  recorridos sin error, escrituras bloqueadas con el mensaje del escaparate y el
  simulador sin incidencias.

## Consecuencias

- La demo enseña la empresa entera, contabilidad incluida, y nadie la ensucia.
- Quien quiera probar a crear cosas no puede hacerlo en la demo pública. Las
  copias por visitante (`panel/sandbox.py`) siguen preparadas por si algún día
  hay servidor para ellas.
