# ADR-001: Migración a Odoo 18

- **Estado**: Aceptado (documentación; la migración real no se ejecuta ahora)
- **Fecha**: 2026-10-09
- **Decisor**: Hermes Agent (gabinete de IT, $ideas) con mandato autónomo de Jorge

## Contexto

El laboratorio corre Odoo 17 con el módulo propio `ODOO_CRM` (Mobiliario del
Hogar). Odoo 18 ya está publicado y en algún momento razonable convendrá
saltar de major. Este ADR fija qué piezas del proyecto hacen fácil la
migración, cuáles la frenan, y el camino que se seguirá. No es un plan de
ejecución: es la decisión de arquitectura que guiará el plan cuando llegue el
momento.

Viene del benchmark de GitHub del 8 de octubre de 2026
(`benchmark-odoo-github.html`), punto 7: OCA/OpenUpgrade como referencia del
procedimiento estándar de upgrade en el ecosistema.

## Qué nos hace FÁCIL la migración

1. **Módulo propio pequeño y delimitado.** Un solo modelo
   (`furniture.product`), dos vistas, un controlador, un CSV de seguridad y un
   CSV de datos. El módulo ya pasa el linter oficial OCA (2026-10-09) y no usa
   APIs eliminadas en 18 (sin `t-esc`, sin nodo `<data>`, sin `string=` en
   tree).
2. **La suite corre sin Odoo.** 87 pruebas sin servidor ni PostgreSQL validan
   catálogo, módulo, panel y asistente. Tras un upgrade, la suite es la red de
   seguridad inmediata: si algo del módulo rompe la instalación o la vista, la
   suite lo cuenta antes de abrir el navegador.
3. **Datos reproducibles por scripts.** El laboratorio se repuebla con los
   scripts de `scripts/` en orden documentado. Una base corrupta por el
   upgrade se puede reconstruir; no hay dato único e irrecuperable en el lab.
4. **Instantánea canónica + restauración probada.** `demo_restaurar_muebles.py`
   restaura la base desde la instantánea con un manifiesto de 14 recuentos
   verificado. El backup antes de migrar ya existe y está probado, no es
   teórico.
5. **Cron de limpieza cada 30 minutos.** Si la migración deja el lab en
   estado raro, el cron lo detecta (compara los 14 recuentos) y restaura.

## Qué nos FRENA la migración

1. **SQL directo contra el esquema interno.** El panel del día consulta el
   contenedor de PostgreSQL con SQL sin ORM (`panel_muebles.py`). Odoo 18
   puede renombrar tablas o campos internos y romper el panel sin aviso.
   Es el punto débil técnico más citado del enfoque "solo lectura con
   stdlib": el contrato estable es la API XML-RPC/JSON-RPC, no el esquema.
2. **Scripts `odoo shell` acoplados al contenedor.** Los scripts de poblado
   corren con `docker exec ... odoo shell`. Un cambio de versión puede
   cambiar flags, rutas de addons o el propio shell: cada script es un punto
   de ruptura manual durante el upgrade.
3. **Vistas con herencia qweb fina.** `panel_template.xml` hereda de
   `website.layout`. Odoo 18 cambió el client (OWL 2) y suelen moverse
   bloques del layout: los xpath de herencia pueden fallar y hay que
   re-verificar la página del panel a mano.
4. **Traducciones es_ES cargadas por script.** `espanolizar_laboratorio.py`
   es el script más grande (28,9 KB) y el que más APIs de traducción toca;
   es el candidato número uno a dolores de migración (las APIs de
   traducción cambian entre majors).

## Decisión

1. **No migrar ahora.** El lab funciona en 17, la candidatura no necesita el
   salto hoy y migrar en frío "porque salió la versión" no es señal de
   madurez. La migración real se decide con un trigger explícito (p. ej.
   preparación de entrevista con demo sobre 18, o implantación real).
2. **Adoptar el procedimiento OCA/OpenUpgrade cuando llegue el momento**:
   análisis previo con OpenUpgrade analysis mode sobre una copia de la base,
   upgrade del módulo propio primero en local, suite completa, y solo después
   el lab público. Nunca en vivo.
3. **Reducir las fricciones ANTES de migrar**, en este orden:
   - El universo versionado (benchmark punto 1) como fuente de verdad del
     poblado, para que reproducir la base no dependa de 11 scripts en orden
     manual.
   - Migrar el panel a la API JSON-RPC (benchmark punto 4) para desacoplarlo
     del esquema interno.
   - Estas dos mejoras viven en el roadmap; cada una baja el coste de la
     migración futura por separado.
4. **La suite de 87 pruebas es el gate de la migración**: el upgrade se da por
   bueno solo con suite verde + lab vivo respondiendo + almacén cuadrado
   (verificador de recuentos), no por "parece que funciona".

## Consecuencias

- El repo queda documentado para la pregunta de entrevista "¿cómo migrarías
  esto a Odoo 18?": respuesta con nombre propio (OpenUpgrade), orden de
  riesgos y gate de verificación.
- No se instala OpenUpgrade ahora: YAGNI. Es una dependencia pesada para un
  lab que no migra hoy.
- Los hallazgos del linter OCA ya corregidos (2026-10-09) eliminan de antemano
  las rupturas triviales que el upgrade habría encontrado en las vistas.

## Señal de revisión

Revisar este ADR cuando: salga Odoo 19, cuando el panel pase a API
(benchmark punto 4), o cuando el universo versionado (punto 1) aterrice y
 cambie la forma de repoblar el lab.
