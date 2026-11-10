# Seguridad — ODOO_CRM

Alcance: el módulo `ODOO_CRM` (Odoo 20), el panel del día (`panel/`) y el
laboratorio público. Este documento describe lo que hace el código hoy; si
algo de aquí deja de ser cierto, es un fallo y se corrige el código o el texto.

## Credenciales

- En el repositorio no hay claves, tokens ni contraseñas de servicios reales.
  Las de `docker-compose.yml` y `config/odoo.conf` (`odoo`/`odoo`) son las de un
  laboratorio local y la base no se publica fuera de la red de Docker.
- El panel se autentica con la **API key** de un usuario de integración, en la
  variable `MUEBLES_ODOO_API_KEY`. No tiene valor por defecto: si falta, el
  panel lo dice y no lee nada (`panel/configuracion.py`).
- `.env` está en `.gitignore`; `.env.example` lista las variables.
- Hasta la versión 1 el README publicaba la contraseña del usuario de visita de
  la demo. Se ha quitado y sigue en el historial de git, así que se considera
  pública. El despliegue de la v2 (7-nov-2026) la rotó en la demo.

## Usuario de integración del panel

| Qué | Cómo |
|---|---|
| Grupos | *Usuario interno* + *Panel del día: solo lectura* (`security/groups.xml`). |
| Permisos | Solo lectura (`r`) sobre los modelos que consulta el panel (`security/ir.access.csv`). |
| Restricciones | Los permisos de Odoo se suman entre grupos y «Usuario interno» ya puede escribir en algunos modelos (actividades, líneas de movimiento de stock). Por eso hay 17 restricciones `ir.access` sin grupo, activas solo para el grupo del panel, que cierran crear, modificar y borrar en cada modelo que lee (`security/panel_reglas.xml`). Verificado en producción el 9-nov-2026: la clave del panel recibe 403 al escribir en los 10 modelos probados. |
| Clave | Alcance `rpc` (el único que acepta la API JSON-2 de Odoo 20) y caducidad máxima de 90 días, fijada en el grupo. Se rota cada trimestre. |
| Prueba | `tests/test_odoo_permisos_panel.py` comprueba que lee todo lo que necesita y que no puede crear, modificar ni borrar en ninguno de los 17 modelos; el CI intenta escribir por la API con su clave y exige un 403. |

## Acceso a los datos

- El panel lee Odoo **solo** por la API JSON-2 (`POST /json/2/<modelo>/<método>`
  con `Authorization: bearer`). No importa ningún driver de base de datos ni
  ejecuta SQL; una prueba (`tests_estaticos/test_odoo_client.py`) lo vigila.
- Los errores de Odoo se resumen a su mensaje: la traza que Odoo adjunta a las
  respuestas de error no se reenvía al visitante.
- Excepción documentada: la restauración de la demo
  (`panel/demo_restaurar_muebles.py`) carga una instantánea con `psql` dentro
  del contenedor de la base. Es una tarea de operación del servidor, no parte
  de la integración, y no la puede lanzar un visitante.

## Exposición

- Odoo y el panel se publican solo en `127.0.0.1`; fuera llegan a través del
  proxy (Caddy) del servidor. El panel escucha en `127.0.0.1` salvo que
  `MUEBLES_PANEL_HOST` diga otra cosa (en Docker, dentro del contenedor).
- PostgreSQL no publica puerto en `docker-compose.yml`.

## Panel y asistente públicos

- El panel pinta todo lo que viene de Odoo con `textContent` (nunca `innerHTML`);
  un test lo vigila.
- `/api/preguntar` tiene límite por IP (10/hora), tope global (300/día), tope de
  peticiones simultáneas (2) y cuerpo máximo de 4 KB. Configurables con
  `MUEBLES_LLM_POR_IP_HORA`, `MUEBLES_LLM_GLOBAL_DIA` y `MUEBLES_LLM_CONCURRENTES`.
- La clave del modelo solo se lee de `MUEBLES_LLM_KEY` u `OPENROUTER_API_KEY`
  (entorno); ya no se buscan ficheros del servidor.
- `/api/dia` es público a propósito y solo es apto para datos sintéticos de la demo.

## Sandbox por visitante (todavía no conectado)

`panel/sandbox.py` está implementado y probado, pero **ningún controlador lo usa
aún**: `/demo` sigue abriendo la sesión del usuario `visita`. Clona una base por visitante desde una plantilla, con cookie
firmada HMAC-SHA256 (`MUEBLES_SECRETO`), caducidad y tope de bases simultáneas;
los nombres de base se validan con `muebles_demo_[a-z0-9]{4,12}`.

## Usuario de visita de la demo: escaparate de solo lectura

`/demo` abre sesión como `visita` sin contraseña. Desde el 10-11-2026 está en el
grupo «Escaparate: solo lectura» (`models/escaparate.py`): ve ventas, CRM,
compras, inventario y contabilidad (grupo de Odoo de solo lectura contable),
pero **no puede crear, modificar ni borrar nada en ningún modelo**, tampoco
publicar en el chatter ni confirmar o validar documentos. El cierre no lista
modelos: se aplica en `_access_domain`, el punto por el que pasan todos los
permisos de Odoo 20, así que también cubre módulos futuros, y la interfaz abre
los formularios en lectura. Solo quedan abiertos los asistentes (lo que intenten
escribir en un modelo real vuelve a estar cerrado) y las preferencias y la
presencia de la propia sesión. No tiene «Características técnicas» ni es
administrador.

La limpieza de cada media hora sigue activa como segunda barrera. Límite
conocido: las preferencias del usuario (idioma, zona horaria) son de un usuario
compartido; si alguien las cambia, las ven los siguientes visitantes hasta que
se restauren. Esto es aceptable solo con datos sintéticos: no conectar nunca
datos reales.

## Servidor

- Los servicios están versionados en `scripts/systemd/`; la instalación paso a
  paso está en [`scripts/systemd/LEEME.md`](scripts/systemd/LEEME.md).
- El panel, que es lo expuesto detrás del proxy, corre con el usuario de sistema
  `muebles-panel`, sin shell: ve el código en solo lectura y solo escribe en su
  caché. No toca Docker ni la base. Lo único privilegiado que puede hacer es
  `sudo systemctl start muebles-restore-ahora.service` (regla de sudo de una
  línea, sin argumentos libres); esa unidad, como root, es la que restaura.
- Todos los correos de la demo usan dominios reservados (`.example`): el
  simulador sustituye en cada tramo cualquier dirección real, también la que
  escriba un visitante, y borra sin enviar los correos que deje en cola.
- El temporizador lanza `limpieza_automatica.sh`: primero verifica los recuentos
  en solo lectura y solo restaura si no cuadran. Una demo intacta no se para.
- La demo corre sobre PostgreSQL 17 y Odoo arranca sin `--dev`.

## Pendiente

- Conectar `panel/sandbox.py` (una base por visitante) si la demo pasa a tener
  datos que no deban compartirse.
- El asistente del panel está sin clave de modelo en el servidor: responde con
  los fragmentos del repositorio. Para activar la redacción por IA, poner
  `MUEBLES_LLM_KEY` en `/etc/muebles/panel.env`.

## Si se filtra una credencial

1. Revocarla o rotarla en Odoo (Preferencias → Seguridad de la cuenta → claves API).
2. Revisar el registro de accesos del proxy.
3. Si estaba en git, asumir que es pública aunque se borre del fichero.
