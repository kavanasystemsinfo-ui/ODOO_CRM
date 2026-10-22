"""Test de extremo a extremo que simula un comercial usando el panel y la capa MCP."""

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

# Add the ODOO_CRM root to sys.path so we can import models and panel
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / 'panel'))


def test_e2e_comercial_mcp():
    """Prueba de extremo a extremo: comercial consulta panel -> obtiene lead -> usa MCP.sugerir_accion."""
    # Import panel module
    spec = importlib.util.spec_from_file_location('panel_muebles', RAIZ / 'panel' / 'panel_muebles.py')
    panel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(panel)
    # Import MCP module
    spec_mcp = importlib.util.spec_from_file_location('mcp', RAIZ / 'models' / 'mcp.py')
    mcp_module = importlib.util.module_from_spec(spec_mcp)
    spec_mcp.loader.exec_module(mcp_module)

    try:
        cifras = panel.leer_cifras()
    except RuntimeError as e:
        # If the laboratory is not available, skip the test
        pytest.skip(f"Laboratorio no disponible: {e}")
    # Ensure mcp_sugerencia is present
    assert "mcp_sugerencia" in cifras, "Campo mcp_sugerencia falta en la salida del panel"
    # Hardcoded lead data as used in the panel
    lead_data = {
        "score_kavana": 85,
        "senales": {
            "tipo_contrato": True,
            "proyecto_referenciado": False,
            "muestra_pedida": True,
            "email_corporativo": False,
            "contacto_reciente": False,
        },
        "prioridad_sugerida": "alta",
    }
    expected = mcp_module.MCPService.sugerir_accion(lead_data)
    actual = cifras["mcp_sugerencia"]
    assert actual == expected, f"Se esperaba {expected!r}, se obtuvo {actual!r}"
