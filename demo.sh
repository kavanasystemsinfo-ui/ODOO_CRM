#!/usr/bin/env bash
# Demo script for Odoo CRM panel and MCP integration
# Usage: ./demo.sh

set -e

echo "=== Demo del panel del día y capa MCP ==="
echo

echo "1. Verificando que el laboratorio está en marcha..."
if ! curl -s http://127.0.0.1:8081/api/dia > /dev/null; then
  echo "Error: No se puede contactar al panel. Asegúrese de que el laboratorio esté en marcha."
  echo "   Puede iniciarlo con: docker compose -f ./docker-compose.yml up -d"
  exit 1
fi
echo "   OK: Panel respondiendo"
echo

echo "2. Obteniendo datos del panel (endpoint /api/dia)..."
DATA=$(curl -s http://127.0.0.1:8081/api/dia)
echo "$DATA" | python3 -m json.tool | head -30
echo

echo "3. Extrayendo la sugerencia MCP..."
MCP_SUGERENCIA=$(echo "$DATA" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('mcp_sugerencia', 'NOT FOUND'))")
echo "   Sugerencia MCP: $MCP_SUGERENCIA"
echo

echo "4. Mostrando el flujo de extremo a extremo (comercial usando panel + MCP)..."
echo "   El comercial consulta el panel para obtener el estado actual del laboratorio..."
echo "   Luego utiliza la capa MCP para obtener una sugerencia de acción basada en los datos."
echo
echo "   Simulación:"
echo "   - Score: 85 (alto)"
echo "   - Señal muestra_pedida: true"
echo "   - Prioridad sugerida: alta"
echo "   → Sugerencia: Coordinar visita física para mostrar materiales y acabados (score: 85)"
echo
echo "5. Verificando que la sugerencia coincide con la esperada..."
ESPERADA="Coordinar visita física para mostrar materiales y acabados (score: 85)"
if [ "$MCP_SUGERENCIA" = "$ESPERADA" ]; then
  echo "   ✓ La sugerencia coincide con la esperada."
else
  echo "   ✗ La sugerencia no coincide."
  echo "   Esperado: $ESPERADA"
  echo "   Obtenido: $MCP_SUGERENCIA"
fi
echo

echo "Demo completada."
