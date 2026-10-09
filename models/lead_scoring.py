"""Scoring determinista y explicable de oportunidades del CRM.

Patrón tomado del benchmark (2026-10-08, punto 6: yunsBRB/odoo-lead-scoring):
cinco señales de negocio puntúan de 0 a 100, la prioridad se sugiere pero
aplicarla es decisión humana, y el score se recalcula al leer para que las
señales viejas no sigan puntuando.

Aquí la puntuación es una FUNCIÓN PURA (`puntuar`) testeable sin Odoo; el
modelo Odoo (crm.lead heredado) solo la invoca. Sin cajas negras: cada señal
vale lo que la tabla dice y el código es 20 líneas.
"""
from __future__ import annotations

# Señales del sector mueblero (laboratorio Muebles del Hogar S.L.):
#   - tipo de cliente: contract/estudio compra en serie (25)
#   - superficie o proyecto: hay número de referencia de proyecto (20)
#   - muestra pedida: pidieron ver catálogo físico o muestra (30)
#   - email verificado: dominio corporativo, no gratuito (10)
#   - contacto reciente: contacto en los últimos 7 días (15)
PESOS = {
    "tipo_contrato": 25,
    "proyecto_referenciado": 20,
    "muestra_pedida": 30,
    "email_corporativo": 10,
    "contacto_reciente": 15,
}

# Umbrales de prioridad sugerida (la aplicación sigue siendo explícita).
UMBRAL_ALTA = 75
UMBRAL_MEDIA = 50
UMBRAL_BAJA = 25


def puntuar(señales: dict[str, bool]) -> int:
    """Suma los pesos de las señales activas. Determinista y explicable."""
    return sum(peso for nombre, peso in PESOS.items() if señales.get(nombre))


def prioridad_sugerida(score: int) -> str:
    """Prioridad sugerida a partir del score. Aplicarla es cosa del comercial."""
    if score >= UMBRAL_ALTA:
        return "alta"
    if score >= UMBRAL_MEDIA:
        return "media"
    if score >= UMBRAL_BAJA:
        return "baja"
    return "ninguna"


def es_email_corporativo(email: str | None) -> bool:
    """True si el dominio no es de un proveedor gratuito habitual."""
    if not email or "@" not in email:
        return False
    dominio = email.rsplit("@", 1)[1].lower()
    return dominio not in {
        "gmail.com", "hotmail.com", "outlook.com", "yahoo.com",
        "hotmail.es", "yahoo.es", "protonmail.com",
    }
