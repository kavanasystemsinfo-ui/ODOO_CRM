# ADR-005: copias de prueba por visitante, en el mismo servidor

- **Estado**: aceptado
- **Fecha**: 2026-11-10

## Contexto

El escaparate (ADR-004) deja mirar, pero no probar. La idea era que cada
visitante pudiera usar Odoo con libertad sin ensuciar la demo y sin pagar más
servidor (VPS de 4 GB).

Se descartó guardar los cambios en el navegador o borrar cookies: en Odoo la
cookie solo identifica la sesión. Confirmar un pedido crea el albarán, reserva
stock y genera apuntes en la base del servidor. Borrar la cookie no deshace
nada, y simular Odoo en el navegador no tendría sus reglas de negocio.

## Decisión

Cada visitante que lo pide recibe una **copia privada de la base que caduca a
la hora**. Hay 3 copias a la vez como máximo, que es lo que cabe en memoria.

- **Plantilla**: en cada tramo de la empresa simulada se construye
  `muebles_plantilla` a partir de la instantánea canónica, neutralizada con la
  herramienta oficial de Odoo (sin tareas programadas ni correo, y con el aviso
  de base de pruebas) y con el usuario `probador`. El probador tiene ventas,
  compras, almacén y facturación, pero no Ajustes.
- **Crear** (`/probar` → `/probar/crear`, en el Odoo de la demo): un POST con
  CSRF clona la plantilla con `CREATE DATABASE … TEMPLATE` y copia sus ficheros.
  El Odoo de la demo nunca carga la copia en memoria. La caducidad se guarda en
  la propia base (`COMMENT ON DATABASE`) y el navegador recibe una cookie
  firmada con HMAC-SHA256 que dura lo mismo.
- **Enrutar**: Caddy manda a quien lleva la cookie a un segundo proceso de
  Odoo (`furniture_odoo_pruebas`). Es la misma imagen, el mismo código y los
  mismos ficheros, pero solo ve `muebles_demo_*`, no tiene tareas programadas
  y su memoria está limitada a 1,2 GB. Sin DNS nuevo y en el mismo dominio.
- **Entrar** (`/probar/entrar`, en el Odoo de pruebas): ODOO_CRM se carga ahí
  como módulo de servidor para que la ruta funcione antes de tener base. Valida
  la cookie y abre la sesión del probador con `finalize()`, como `/demo`, sin
  contraseña.
- **Borrar**: `muebles-pruebas-limpieza.timer` borra cada 5 minutos las copias
  caducadas (5 minutos de gracia) con sus ficheros. Odoo no suelta de memoria
  el registro de una base borrada, así que el Odoo de pruebas se reinicia
  cuando nadie está probando, o cuando ya acumula 3 registros muertos.

## Por qué así y no de otra forma

- **Un solo Odoo con varias bases**: en cuanto existiera una copia, la tienda
  pública y la demo dejarían de saber qué base servir. Odoo 20 elige la base
  por la sesión o porque solo hay una; ya no acepta `?db=`.
- **Un subdominio por copia**: necesitaría un comodín en el DNS. La cookie da
  lo mismo sin tocar el dominio.
- **`odoo.modules.db.duplicate()`**: carga la copia en la memoria del proceso
  que la crea, que sería el de la demo.

## Verificación

- Tests estáticos:
  - la firma no se puede falsificar ni alargar y no apunta a la copia de otro;
  - qué se borra y cuándo reiniciar;
  - que el Odoo de pruebas solo ve copias, sin gestor de bases ni tareas
    programadas;
  - la regla de Caddy.
- Tests de Odoo (HTTP):
  - sin secreto no hay copias;
  - con las plazas llenas avisa y no crea;
  - crear exige POST con CSRF;
  - la entrada no hace nada en el Odoo de la demo.
- Ensayo en el VPS con un Odoo de pruebas temporal: plantilla real, entrada,
  sesión del probador, pedido creado y confirmado en la copia, Ajustes
  bloqueado, demo intacta (56 pedidos frente a 57 en la copia), 164 MB con una
  copia, y borrado con reinicio.

## Consecuencias

- Mirar sigue siendo el escaparate (`/demo`). Probar es `/probar`.
- Si coinciden más de 3 personas, la cuarta ve cuándo queda libre la siguiente
  plaza.
- Si alguien borra la cookie de sesión de Odoo pero conserva la de la prueba,
  Odoo le pedirá una base. Basta con volver a `/probar/entrar`.
