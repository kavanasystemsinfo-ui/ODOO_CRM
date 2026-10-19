# Decisiones de Arquitectura y Diseño - ODOO_CRM

Este documento resume las decisiones técnicas clave del proyecto, con enlaces a la documentación detallada y al código.

---

## 1. Arquitectura General: Módulo Odoo Ligero + Panel Externo

**Decisión:** El proyecto se divide en dos partes:
- **Módulo Odoo** (`ODOO_CRM`): Modelo `furniture.product`, vistas, seguridad, datos CSV. Instalable en cualquier Odoo 17.
- **Panel del día** (`panel/`): Servidor HTTP independiente (Python stdlib) que lee Odoo vía JSON-RPC y sirve una UI web simple.

**Razón:** Separación de responsabilidades. El módulo es portable; el panel es una herramienta de demo/visualización que no debe acoplarse al ORM de Odoo.

**Referencias:**
- `__manifest__.py` - Definición del módulo
- `panel/panel_muebles.py` - Panel principal
- `panel/odoo_client.py` - Cliente JSON-RPC (benchmark punto 4)

---

## 2. Cliente JSON-RPC en vez de SQL Directo (Benchmark Punto 4)

**Decisión:** El panel usa `odoorpc` (biblioteca oficial OCA) para consultar Odoo vía JSON-RPC, no SQL directo contra PostgreSQL.

**Razón:** 
- Contrato estable: la API JSON-RPC de Odoo es pública y versionada; el esquema SQL interno cambia entre versiones.
- Migración a Odoo 18 más fácil (ver ADR-001).
- Seguridad: usuario `visita` con permisos mínimos de solo lectura.

**Trade-off:** Ligeramente más lento que SQL directo, pero aceptable para un panel de demo.

**Referencias:**
- `panel/odoo_client.py` - Implementación con cache LRU
- `panel/configuracion.py` - Configuración de conexión
- `docs/adr/ADR-001-migracion-odoo-18.md` - Riesgo #1: SQL directo

---

## 3. Scoring Determinista y Explicable (Benchmark Punto 6)

**Decisión:** El scoring de oportunidades (`lead_scoring.puntuar()`) es una **función pura** sin estado, testeable sin Odoo. Cinco señales de negocio con pesos fijos (total 100). La prioridad se *sugiere*, no se impone.

**Razón:**
- Explicable: cada señal vale lo que dice la tabla, sin cajas negras.
- Determinista: misma entrada → mismo score, sin azar ni IA.
- Recalculado al leer: campos computed no stored en `crm.lead` heredado, así las señales viejas no puntúan.

**Señales y pesos (sector mueblero):**
| Señal | Peso | Descripción |
|-------|------|-------------|
| `tipo_contrato` | 25 | Cliente contract/estudio (compra en serie) |
| `proyecto_referenciado` | 20 | Número de proyecto/obra en conversación |
| `muestra_pedida` | 30 | Pidieron catálogo físico o muestra |
| `email_corporativo` | 10 | Dominio no gratuito |
| `contacto_reciente` | 15 | Actividad en últimos 7 días |

**Referencias:**
- `models/lead_scoring.py` - Lógica pura + tests
- `models/crm_lead_scoring.py` - Integración Odoo (campos computed)
- `views/crm_lead_scoring_views.xml` - UI en formulario y tree
- `tests/test_lead_scoring.py` - 7 tests de la lógica pura

---

## 4. Datos Reproducibles y Verificables

**Decisión:** El laboratorio se pobla mediante scripts ordenados (`scripts/`) a partir de un origen real (80 productos de District Home). El almacén es "cuadrado": 2.190 unidades = suma exacta de movimientos. Existe un **snapshot canónico** (`snapshot_muebles_demo_canonico.sql.gz`) y un script de restauración con **14 recuentos verificados**.

**Razón:**
- Reproducibilidad: cualquiera puede recrear el lab idéntico.
- Verificabilidad: el script `demo_restaurar_muebles.py` falla si los recuentos no cuadran.
- Resiliencia: cron cada 30 min restaura si el lab se corrompe.

**Referencias:**
- `scripts/import_districthome_products.py` - Importación de productos
- `scripts/load_product_images.py` - Carga de imágenes
- `panel/demo_restaurar_muebles.py` - Restauración con manifiesto de 14 recuentos
- `tests/test_verificador.py` - Tests de verificación de recuentos

---

## 5. Panel Honesto: Reglas Deterministas, No IA

**Decisión:** Las frases del panel son **reglas deterministas** (recuentos, umbrales, porcentajes). Si no hay clave de modelo LLM, el panel *declara* que no hay IA en vez de aparentar.

**Razón:** Honestidad visible. Un reclutador o visitante ve exactamente qué es regla y qué sería IA.

**Ejemplo:** `salud_dato` lista campos y dice explícitamente `ok: true/false` con `motivo`. Si falla: "no puedo afirmar nada sobre X".

**Referencias:**
- `panel/panel_muebles.py` - `construir_resumen()`, `formato_numero()`, `_porcentaje()`
- `tests/test_panel_logica.py` - 21 tests de formato y frases

---

## 6. Sandbox por Visitante (Aislamiento)

**Decisión:** Cada visitante clona su propia BD (`muebles_demo_XXXXXXXX`) de una plantilla `muebles_plantilla`. Cookie firmada HMAC-SHA256 con secreto configurable. TTL 4h, tope 3 concurrentes. Plantilla filtrada por Odoo (`^muebles_demo_` regex).

**Razón:** 
- Un visitante puede "romper" su lab sin afectar a otros.
- Botón de reinicio solo afecta a su BD.
- Sin estado compartido entre visitantes.

**Referencias:**
- `panel/sandbox.py` - Lógica pura + operaciones Docker/psql
- `panel/panel_muebles.py` - Endpoint de reinicio (requiere sesión admin Odoo)

---

## 7. MCP Desacoplado (Model Context Protocol)

**Decisión:** Capa `models/mcp.MCPService` con interfaz uniforme. Por defecto: plantillas deterministas (sin API externa). Variable `MCP_EXTERNAL_ENABLED=1` para activar proveedor externo (OpenAI, etc.). Si se activa sin implementar → `NotImplementedError`.

**Razón:** 
- Desacopla el código de Odoo de proveedores de IA.
- Permite demo sin coste de API.
- Extensible para producción real.

**Referencias:**
- `models/mcp.py` - `MCPService`, plantillas por prioridad/señal
- `tests/test_mcp.py` - Tests deterministas
- `tests/test_e2e_comercial_mcp.py` - Test E2E panel → MCP

---

## 8. Formato Español en Todo el Código

**Decisión:** Números: `12.415` (miles), `12.415,50` (decimales). Porcentajes: `85,4 %`. Moneda: `€` con formato español. Fechas: ISO `YYYY-MM-DD`.

**Razón:** Coherencia con el usuario final (empresa española) y estándar acordado con Jorge.

**Referencias:**
- `panel/panel_muebles.py` - `formato_numero()`, `_porcentaje()`
- `tests/test_panel_logica.py` - Tests de formato

---

## 9. CI/CD: GitHub Actions con Suite Dual

**Decisión:** Dos jobs:
- `suite`: 87 tests estáticos (sin Odoo) en cada push a main.
- `vivo-tests`: Tests que requieren lab vivo (`MUEBLES_LAB=1`), programados y manuales.

**Razón:** Feedback rápido en PRs (suite estática) + verificación completa en servidor (vivo).

**Referencias:**
- `.github/workflows/tests.yml`
- `requirements-dev.txt` - `pytest`, `odoorpc`, `oca-odoo-pre-commit-hooks`

---

## 10. Migración a Odoo 18 Documentada (ADR-001)

**Decisión:** No migrar ahora. Cuando toque: usar **OpenUpgrade** (procedimiento OCA), analizar primero, migrar módulo propio en local, suite verde + lab vivo + almacén cuadrado como gate.

**Razón:** 
- Migrar "porque salió la versión" no es señal de madurez.
- ADR documenta riesgos (SQL directo, scripts `odoo shell`, vistas qweb, traducciones) y plan.

**Referencias:**
- `docs/adr/ADR-001-migracion-odoo-18.md`

---

## 11. Seguridad: Sin Credenciales Hardcodeadas

**Decisión:** Usuario y password de JSON-RPC **sin defaults en código**. Obligatorios vía variables de entorno `MUEBLES_JSONRPC_USER` y `MUEBLES_JSONRPC_PASSWORD`. Lanzan `RuntimeError` si faltan.

**Razón:** 
- Cumple `SECURITY.md`.
- Evita fugas accidentales en repositorio/logs.
- Demo pública configurable sin tocar código.

**Referencias:**
- `panel/configuracion.py` - `odoo_jsonrpc_user()`, `odoo_jsonrpc_password()`
- `SECURITY.md` - Política completa

---

## 12. Imports Lazy para Dependencias Opcionales

**Decisión:** `mcp` y `lead_scoring` se importan *dentro* de `leer_cifras()` (lazy), no en top-level. Si faltan, el panel arranca y usa fallback determinista.

**Razón:** El panel no debe romperse por dependencias opcionales de demo.

**Referencias:**
- `panel/panel_muebles.py` - `leer_cifras()` líneas ~336-340

---

## 13. Tests Reales, No Mocks

**Decisión:** 119 tests (112 pasan, 8 skipped por requerir lab vivo). Los tests estáticos validan lógica pura, formato, catálogo, módulo, sandbox, asistente. Los tests vivo validan integración real con Odoo/PostgreSQL.

**Razón:** Confianza real. Mocks ocultan problemas de integración.

**Referencias:**
- `tests/conftest.py` - Fixtures compartidas
- `pytest.ini` - Marcador `vivo` para tests que necesitan lab

---

## Próximas Decisiones Pendientes (Roadmap)

1. ~~**Migrar panel 100% a JSON-RPC**~~ ~~- Eliminar cualquier resto de SQL directo (ya hecho en panel, verificar `odoo_client.py` cubre todo).~~ ✅ **COMPLETADO**
2. **`docker-compose.yml` en raíz** + `demo.sh` portable.
3. **Separar landing/video** a `demo/` o repo `ODOO_CRM-demo`.
4. **`pyproject.toml`** con `ruff`, `black`, `mypy`, `pre-commit`.
5. **README técnico** ampliado (Arquitectura, Cómo ejecutar tests, Decisiones clave).
6. **Suite verde en GitHub Actions** con badge.
7. **Demo grabada** (GIF) en README.

---

*Última actualización: 2026-10-18*
*Mantenido por: Hermes Agent (asistente de KAVANA Systems)*
