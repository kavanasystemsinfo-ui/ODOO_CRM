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
  la demo. Se ha quitado, pero **sigue en el historial de git**: esa contraseña
  debe rotarse en la demo pública.

## Usuario de integración del panel

| Qué | Cómo |
|---|---|
| Grupos | *Usuario interno* + *Panel del día: solo lectura* (`security/groups.xml`). |
| Permisos | Solo lectura (`r`) sobre los modelos que consulta el panel (`security/ir.access.csv`). |
| Clave | Alcance `rpc` (el único que acepta la API JSON-2 de Odoo 20) y caducidad máxima de 90 días, fijada en el grupo. Se rota cada trimestre. |
| Prueba | `tests/test_odoo_permisos_panel.py` comprueba que lee todo lo que necesita y que no puede crear, modificar ni borrar; el CI intenta escribir por la API con su clave y exige un 403. |

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

## Pendiente

- Rotar la contraseña del usuario de visita de la demo (ver arriba).
- La demo pública devuelve trazas de Python en las respuestas de error de la
  API (modo desarrollador o `--dev` en el servidor). Conviene desactivarlo.
- La demo pública corre sobre PostgreSQL 15; Odoo 20 necesita 16 o superior.

## Si se filtra una credencial

1. Revocarla o rotarla en Odoo (Preferencias → Seguridad de la cuenta → claves API).
2. Revisar el registro de accesos del proxy.
3. Si estaba en git, asumir que es pública aunque se borre del fichero.
