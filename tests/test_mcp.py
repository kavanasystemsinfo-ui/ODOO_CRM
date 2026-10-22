import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "models"))

from mcp import MCPService

def test_mcp_sugerir_accion_alta_muestra():
    lead = {
        'score_kavana': 85,
        'senales': {
            'tipo_contrato': True,
            'proyecto_referenciado': False,
            'muestra_pedida': True,
            'email_corporativo': False,
            'contacto_reciente': False,
        },
        'prioridad_sugerida': 'alta',
    }
    sugerencia = MCPService.sugerir_accion(lead)
    assert isinstance(sugerencia, str)
    assert len(sugerencia) > 0
    # En modo determinista (externo deshabilitado) debería retornar una de las esperadas con score
    assert "Coordinar visita física" in sugerencia
    assert "(score: 85)" in sugerencia

def test_mcp_sugerir_accion_media_email():
    lead = {
        'score_kavana': 60,
        'senales': {
            'tipo_contrato': False,
            'proyecto_referenciado': False,
            'muestra_pedida': False,
            'email_corporativo': True,
            'contacto_reciente': False,
        },
        'prioridad_sugerida': 'media',
    }
    sugerencia = MCPService.sugerir_accion(lead)
    assert isinstance(sugerencia, str)
    assert len(sugerencia) > 0
    assert "Enviar catálogo digital" in sugerencia
    assert "(score: 60)" in sugerencia

def test_mcp_sugerir_accion_baja():
    lead = {
        'score_kavana': 30,
        'senales': {
            'tipo_contrato': True,
            'proyecto_referenciado': False,
            'muestra_pedida': False,
            'email_corporativo': False,
            'contacto_reciente': False,
        },
        'prioridad_sugerida': 'baja',
    }
    sugerencia = MCPService.sugerir_accion(lead)
    assert isinstance(sugerencia, str)
    assert len(sugerencia) > 0
    assert "Invitar a webinar" in sugerencia
    assert "(score: 30)" in sugerencia

def test_mcp_es_habilitado_defecto():
    # Por defecto, la variable de entorno no está establecida
    # Pero podemos asegurarnos de que el valor por defecto sea False
    # Guardamos y restauramos el entorno
    old = os.environ.get("MCP_EXTERNAL_ENABLED")
    if "MCP_EXTERNAL_ENABLED" in os.environ:
        del os.environ["MCP_EXTERNAL_ENABLED"]
    try:
        assert MCPService.es_habilitado() is False
    finally:
        if old is not None:
            os.environ["MCP_EXTERNAL_ENABLED"] = old
        elif "MCP_EXTERNAL_ENABLED" in os.environ:
            del os.environ["MCP_EXTERNAL_ENABLED"]

def test_mcp_externo_not_implementado():
    old = os.environ.get("MCP_EXTERNAL_ENABLED")
    os.environ["MCP_EXTERNAL_ENABLED"] = "1"
    try:
        # Recargar el módulo para que vea la nueva variable de entorno
        import importlib
        import mcp
        importlib.reload(mcp)
        from mcp import MCPService
        lead = {}
        try:
            MCPService.sugerir_accion(lead)
            assert False, "Se esperaba NotImplementedError"
        except NotImplementedError:
            pass  # esperado
    finally:
        if old is not None:
            os.environ["MCP_EXTERNAL_ENABLED"] = old
        elif "MCP_EXTERNAL_ENABLED" in os.environ:
            del os.environ["MCP_EXTERNAL_ENABLED"]
        # Recargar nuevamente para dejar limpio
        import importlib
        import mcp
        importlib.reload(mcp)