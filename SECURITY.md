# Política de Seguridad - ODOO_CRM

## Alcance
Este documento describe las prácticas de seguridad para el módulo ODOO_CRM (laboratorio de empresa ficticia de muebles sobre Odoo 17).

## Manejo de Credenciales y Secrets

### Principio Fundamental
**NUNCA se commitean credenciales, passwords, tokens o claves API al repositorio.**

### Variables de Entorno Obligatorias
Las siguientes variables DEBEN configurarse en el entorno de ejecución (no tienen defaults en el código):

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `MUEBLES_JSONRPC_USER` | Usuario para conexión JSON-RPC a Odoo | `visita` |
| `MUEBLES_JSONRPC_PASSWORD` | Password para conexión JSON-RPC a Odoo | `password-seguro` |
| `MUEBLES_DB` | Nombre de la base de datos PostgreSQL | `furniture_db` |
| `MUEBLES_JSONRPC_HOST` | Host del servidor Odoo JSON-RPC | `127.0.0.1` |
| `MUEBLES_JSONRPC_PORT` | Puerto del servidor Odoo JSON-RPC | `8070` |
| `MUEBLES_JSONRPC_DB` | Base de datos para JSON-RPC | `furniture_db` |
| `MUEBLES_SNAPSHOT` | Ruta al snapshot SQL canónico | `/ruta/al/snapshot.sql.gz` |

### En Desarrollo Local
- Usar archivo `.env` (NO commiteado, en `.gitignore`)
- Ejemplo `.env.example` incluido para referencia

### En CI/CD (GitHub Actions)
- Configurar como **Repository Secrets** en Settings > Secrets and variables > Actions
- NUNCA escribir secrets en logs de Actions
- Usar `env:` en el workflow para inyectar desde secrets

### En Producción / Demo Pública
- Configurar en el sistema de despliegue (Docker env, systemd EnvironmentFile, etc.)
- Rotar credenciales periódicamente
- Usar usuarios con privilegios mínimos (usuario `visita` solo lectura)

## Acceso a Datos

### Panel del Día
- **Solo lectura**: El panel no escribe en la base de datos
- Conexión vía **JSON-RPC oficial** (biblioteca `odoorpc` de OCA)
- No hay SQL directo contra PostgreSQL (desacopla de esquema interno)

### Sandbox por Visitante
- Cada visitante recibe su propia BD clonada de plantilla
- Cookie firmada con HMAC-SHA256 (secreto configurable por `MUEBLES_SECRETO`)
- TTL configurable (default 4 horas) y tope de BDs concurrentes
- Plantilla `muebles_plantilla` no servida nunca (filtrada por Odoo)

## Dependencias
- `odoorpc>=0.10` (cliente JSON-RPC oficial de OCA)
- `pytest>=8` (solo tests)
- `oca-odoo-pre-commit-hooks>=0.2` (lint OCA)
- Sin dependencias con vulnerabilidades conocidas (verificar con `pip audit`)

## Validación de Entradas
- Validación de nombres de BD en sandbox (`muebles_demo_[a-z0-9]{4,12}`)
- Validación de cookies HMAC antes de usar
- Sanitización de entradas en panel y asistente

## Auditoría y Logs
- Logs de acceso al panel (IP, timestamp, acción)
- No se loguean credenciales ni datos sensibles
- Logs rotados con retención configurable

## Incidencias
Si se detecta una fuga de credenciales:
1. Rotar inmediatamente las credenciales comprometidas
2. Revisar logs de acceso
3. Actualizar este documento si hay cambios en procedimientos

## Referencias
- Benchmark punto 4: Panel por API JSON-RPC en vez de SQL directo
- Benchmark punto 6: Scoring determinista, explicable, sin IA
- ADR-001: Migración a Odoo 18 (docs/adr/ADR-001-migracion-odoo-18.md)
