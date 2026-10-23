from __future__ import annotations

import os
from typing import Any, Dict

# Configuración simple: variable de entorno para activar MCP externo
# En producción, se podría leer de ir.config_parameter o similar.
_EXTERNAL_MCP_ENABLED = os.getenv("MCP_EXTERNAL_ENABLED", "0") == "1"

class MCPService:
    """Capa MCP (Model Context Protocol) para enriquecer leads de CRM.

    Proporciona una interfaz uniforme para obtener sugerencias de acciones
    o enriquecimiento de datos usando modelos externos (OpenAI, etc.) o
    una alternativa determinista cuando no se quiere depender de APIs externos.

    El objetivo es desacoplar el código de Odoo de cualquier proveedor específico
    de IA, permitiendo cambiar la implementación sin tocar el core.
    """

    # Plantillas de prompt para la alternativa determinista.
    # Cada plantilla puede usar placeholders como {score}, {senal_tipo_contrato}, etc.
    _PROMPT_TEMPLATES = {
        # prioridad alta
        ("alta", "muestra_pedida"): "Coordinar visita física para mostrar materiales y acabados (score: {score})",
        ("alta", "proyecto_referenciado"): "Enviar propuesta detallada con plazos y presupuesto (score: {score})",
        ("alta", None): "Llamar para confirmar requisitos y cerrar la venta (score: {score})",
        # prioridad media
        ("media", "muestra_pedida"): "Enviar catálogo y concertar una muestra en el taller (score: {score})",
        ("media", "proyecto_referenciado"): "Enviar propuesta con plazos y presupuesto (score: {score})",
        ("media", "email_corporativo"): "Enviar catálogo digital y solicitar reunión virtual (score: {score})",
        ("media", None): "Seguimiento por email con información de productos destacados (score: {score})",
        # prioridad baja / ninguna
        ("baja", "tipo_contrato"): "Invitar a webinar sobre tendencias en contract (score: {score})",
        ("baja", None): "Enviar el catálogo digital y mantener el seguimiento (score: {score})",
        ("ninguna", None): "Mantener en nurturing mensual con newsletter sectorial (score: {score})",
    }

    @staticmethod
    def _build_context(lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Construye el diccionario de variables para renderizar plantillas."""
        senales = lead_data.get("senales", {})
        return {
            "score": lead_data.get("score_kavana", 0),
            "senal_tipo_contrato": senales.get("tipo_contrato", False),
            "senal_proyecto_referenciado": senales.get("proyecto_referenciado", False),
            "senal_muestra_pedida": senales.get("muestra_pedida", False),
            "senal_email_corporativo": senales.get("email_corporativo", False),
            "senal_contacto_reciente": senales.get("contacto_reciente", False),
            "prioridad": lead_data.get("prioridad_sugerida", "ninguna"),
        }

    @staticmethod
    def _seleccionar_plantilla(prioridad: str, senales: Dict[str, bool]) -> str:
        """Selecciona la plantilla más específica disponible."""
        # Orden de señal de mayor a menor especificidad dentro de cada prioridad
        orden_senales = [
            "muestra_pedida",
            "proyecto_referenciado",
            "tipo_contrato",
            "email_corporativo",
            "contacto_reciente",
        ]
        # Primero buscamos una combinación (prioridad, señal) donde la señal sea True
        for senal in orden_senales:
            if senales.get(senal, False):
                key = (prioridad, senal)
                if key in MCPService._PROMPT_TEMPLATES:
                    return MCPService._PROMPT_TEMPLATES[key]
        # Si no hay señal verdadera, usamos la plantilla genérica para la prioridad
        key_gen = (prioridad, None)
        if key_gen in MCPService._PROMPT_TEMPLATES:
            return MCPService._PROMPT_TEMPLATES[key_gen]
        # Último recurso: plantilla genérica de ninguna
        return MCPService._PROMPT_TEMPLATES[("ninguna", None)]

    @staticmethod
    def sugerir_accion(lead_data: Dict[str, Any]) -> str:
        """Devuelve una sugerencia de acción basada en los datos del lead.

        Args:
            lead_data: Diccionario con al menos los campos:
                - score_kavana (int 0-100)
                - senales (dict[str, bool]): tipo_contrato, proyecto_referenciado,
                                            muestra_pedida, email_corporativo,
                                            contacto_reciente
                - prioridad_sugerida (str): "ninguna", "baja", "media", "alta"

        Returns:
            Cadena de texto con la sugerencia de acción (en español).
        """
        if _EXTERNAL_MCP_ENABLED:
            # Placeholder para integración externa real
            # En una implementación completa, aquí se llamaría a la API de OpenAI
            # o a cualquier otro servicio MCP compatible.
            raise NotImplementedError(
                "MCP externo habilitado pero no implementado. "
                "Definir MCPService._llm_call() o similar."
            )

        # Lógica determinista basada en plantillas
        score = lead_data.get("score_kavana", 0)
        senales = lead_data.get("senales", {})
        prioridad = lead_data.get("prioridad_sugerida", "ninguna")
        contexto = MCPService._build_context(lead_data)
        plantilla = MCPService._seleccionar_plantilla(prioridad, senales)
        # Renderizar placeholders simples {variable}
        try:
            return plantilla.format(**contexto)
        except KeyError:
            # Si falta algún placeholder, devolvemos la plantilla sin renderizar
            return plantilla

    @staticmethod
    def es_habilitado() -> bool:
        """Indica si el MCP externo está habilitado."""
        return _EXTERNAL_MCP_ENABLED

    @staticmethod
    def construir_prompt(lead_data: Dict[str, Any]) -> str:
        """Construye el prompt completo que se enviaría a un LLM externo.
        Esto es útil para testing o para depurar qué se enviaría al modelo.

        Returns:
            Cadena de texto con el prompt (en español).
        """
        # En esta versión determinista, el prompt es la misma sugerencia
        # pero podríamos enriquecerlo con más contexto si quisiera.
        sugerencia = MCPService.sugerir_accion(lead_data)
        return f"Eres un asistente comercial de muebles. Con los siguientes datos del lead: {lead_data}. Sugiere la mejor acción comercial a tomar. Respuesta: {sugerencia}"