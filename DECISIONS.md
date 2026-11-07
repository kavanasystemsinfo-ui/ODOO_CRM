# Decisiones del laboratorio ODOO_CRM

Resumen de las decisiones técnicas, con el código que las aplica y la prueba
que las vigila. La v2 (noviembre de 2026) corrigió varias que decían una cosa
y el código hacía otra; el detalle está en
[ADR-002](docs/adr/ADR-002-modelo-nativo-y-api.md).

---

## 1. Módulo pequeño sobre lo nativo + panel externo

**Decisión:** el módulo `ODOO_CRM` amplía modelos nativos (`product.template`,
`crm.lead`) en lugar de crear modelos paralelos. El panel del día es un
servidor aparte que solo lee Odoo por su API.

**Razón:** una sola ficha de producto y un solo stock; el panel se despliega y
se cambia sin tocar Odoo.

**Código y pruebas:** `models/`, `panel/`, `tests/test_odoo_producto.py`.

---

## 2. El panel lee por la API JSON-2, nunca por SQL

**Decisión:** `panel/odoo_client.py` llama a `POST /json/2/<modelo>/<método>`
con la API key de un usuario de integración de solo lectura (grupo «Panel del
día: solo lectura», clave `rpc`, 90 días como máximo). Librería estándar, sin
`odoorpc` ni `psycopg2`.

**Razón:** permisos, reglas de registro y campos calculados del ORM se
respetan; el score lo calcula el módulo y el panel solo lo lee.

**Historia:** hasta la v1 el panel hacía 35 consultas SQL con usuario y
contraseña fijos, aunque este documento decía que ya usaba JSON-RPC.

**Código y pruebas:** `panel/odoo_client.py`, `security/`,
`tests_estaticos/test_odoo_client.py`, `tests/test_odoo_permisos_panel.py`,
`ci/probar_panel_api.py` (contra Odoo 20 real en el CI).

---

## 3. Scoring determinista y explicable

**Decisión:** la puntuación es una función pura (`lead_scoring.puntuar()`):
cinco señales con pesos fijos que suman 100. La prioridad se *sugiere*; aplicarla
es decisión del comercial. Los campos de `crm.lead` no se guardan (se recalculan
al leer) y todos declaran `@api.depends`.

| Señal | Peso | Cómo se obtiene |
|---|---|---|
| `tipo_contrato` | 25 | Marcada por el comercial (contract, interiorismo, distribución) |
| `proyecto_referenciado` | 20 | Marcada por el comercial |
| `muestra_pedida` | 30 | Marcada por el comercial |
| `email_corporativo` | 10 | Dominio del email no gratuito |
| `contacto_reciente` | 15 | Correo, mensaje al cliente o actividad **hecha** en los últimos 7 días |

**Por qué así el contacto:** en la v1 se usaba la fecha límite de las
actividades, y una llamada planificada para mañana contaba como contacto hecho.

**Código y pruebas:** `models/lead_scoring.py`, `models/crm_lead_scoring.py`,
`tests_estaticos/test_lead_scoring.py`, `tests/test_odoo_scoring.py`.

---

## 4. Datos reproducibles

**Decisión:** el laboratorio se puebla con scripts ordenados
(`data/universo.json` → `scripts/`) a partir de un origen real (80 productos de
District Home). La demo pública se restaura cada media hora desde una
instantánea canónica, y `panel/demo_restaurar_muebles.py` comprueba 14 recuentos
tras restaurar.

**Matiz:** las existencias no son la suma aritmética de los movimientos (el
almacén se sembró con un ajuste y hay transferencias internas); el panel mide si
cada referencia con stock tiene movimientos hechos.

**Código y pruebas:** `scripts/`, `panel/demo_restaurar_muebles.py`,
`tests_estaticos/test_verificador.py`, `tests_estaticos/test_universo.py`.

---

## 5. Panel honesto: reglas deterministas

**Decisión:** las frases del panel son reglas (recuentos, umbrales,
porcentajes). Si no hay clave de modelo de IA, el panel lo declara. La sección
«salud del dato» dice qué no puede afirmar y por qué.

**Código y pruebas:** `panel/panel_muebles.py` (`construir_resumen()`),
`tests_estaticos/test_panel_logica.py`.

---

## 6. Sandbox por visitante

**Decisión:** cada visitante clona su base (`muebles_demo_XXXX`) desde
`muebles_plantilla`, con cookie firmada HMAC-SHA256, caducidad de 4 horas y tope
de 3 bases simultáneas.

**Código y pruebas:** `panel/sandbox.py`, `tests_estaticos/test_sandbox.py`.

---

## 7. Sugerencias comerciales (no es MCP)

**Decisión:** `models/mcp.py` (`MCPService`) elige una plantilla de acción según
la prioridad y las señales. Es determinista y está preparada para enchufar un
proveedor de IA; con `MCP_EXTERNAL_ENABLED=1` lanza `NotImplementedError`
porque esa conexión **no existe todavía**.

**Matiz:** pese al nombre, no implementa el Model Context Protocol. El nombre
se mantiene por compatibilidad con pruebas y panel.

**Código y pruebas:** `models/mcp.py`, `tests_estaticos/test_mcp.py`,
`tests_estaticos/test_e2e_comercial_mcp.py`.

---

## 8. Formato español

**Decisión:** números `12.415` y `12.415,50`, porcentajes `85,4 %`, euros,
fechas ISO.

**Código y pruebas:** `panel/panel_muebles.py` (`formato_numero()`),
`tests_estaticos/test_panel_logica.py`.

---

## 9. CI: pruebas sobre Odoo real y suite sin Odoo

**Decisión:**

- `odoo.yml`: imagen oficial de Odoo 20 + PostgreSQL 17. Instalación en base
  vacía con pruebas `TransactionCase`, panel de extremo a extremo por la API y
  actualización desde la v1.
- `tests.yml`: linter OCA, suite sin Odoo (`tests_estaticos/`) y pruebas contra
  la demo pública (`MUEBLES_LAB=1`).

**Razón:** las pruebas que leen el texto del código no demuestran que el módulo
se instale. Montar las de verdad destapó que Odoo 20 exige PostgreSQL 16+ y que
JSON-2 solo acepta claves `rpc`.

---

## 10. Migraciones del módulo con scripts de Odoo

**Decisión:** los cambios de esquema que afectan a datos se hacen con
`migrations/<versión>/pre-migrate.py` y `post-migrate.py`, idempotentes, que
conservan una copia de lo que retiran y dejan en el log lo que no pudieron
emparejar. Cada migración tiene su ensayo en el CI.

**Código y pruebas:** `migrations/20.0.2.0.0/`, job `migracion-v1-a-v2`.

---

## 11. Credenciales fuera del código

**Decisión:** la API key del panel solo llega por `MUEBLES_ODOO_API_KEY`, sin
valor por defecto. La base de datos no publica puerto. Ver
[`SECURITY.md`](SECURITY.md).

---

## Pendiente

1. Renombrar los campos `x_` del CRM (migración de columnas).
2. Llevar la v2 a la demo pública (actualizar módulo, usuario de integración,
   nueva instantánea canónica; antes, PostgreSQL 15 → 17).
3. Rotar la contraseña del usuario de visita, que estuvo publicada en el README.
4. Modelar el ciclo completo (facturas, cobros, devoluciones) y una migración
   desde Excel con datos sucios.

*Última actualización: 2026-11-07*
