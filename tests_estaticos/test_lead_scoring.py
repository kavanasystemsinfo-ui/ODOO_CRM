"""Scoring determinista de oportunidades: la lógica pura, sin Odoo.

Regla del benchmark: el score es explicable (cada señal pesa lo que la tabla
dice), se recalcula al leer (nada de scores guardados que caducan mal) y la
prioridad se sugiere, no se impone.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "models"))

import lead_scoring  # noqa: E402


def test_todas_las_senales_suman_100():
    todas = {nombre: True for nombre in lead_scoring.PESOS}
    assert lead_scoring.puntuar(todas) == 100


def test_ninguna_senal_da_cero():
    assert lead_scoring.puntuar({}) == 0
    assert lead_scoring.puntuar({nombre: False for nombre in lead_scoring.PESOS}) == 0


def test_los_pesos_estan_documentados_y_cuadran():
    assert sum(lead_scoring.PESOS.values()) == 100
    # cada señal del sector tiene sentido y nombre en español del dominio
    assert set(lead_scoring.PESOS) == {
        "tipo_contrato", "proyecto_referenciado", "muestra_pedida",
        "email_corporativo", "contacto_reciente",
    }


def test_la_prioridad_sugerida_sigue_los_umbrales():
    assert lead_scoring.prioridad_sugerida(100) == "alta"
    assert lead_scoring.prioridad_sugerida(75) == "alta"
    assert lead_scoring.prioridad_sugerida(74) == "media"
    assert lead_scoring.prioridad_sugerida(50) == "media"
    assert lead_scoring.prioridad_sugerida(49) == "baja"
    assert lead_scoring.prioridad_sugerida(25) == "baja"
    assert lead_scoring.prioridad_sugerida(24) == "ninguna"
    assert lead_scoring.prioridad_sugerida(0) == "ninguna"


def test_un_caso_de_negocio_concreto():
    """Distribuidor con proyecto y muestra pedida: 75, prioridad alta."""
    señales = {
        "tipo_contrato": True,
        "proyecto_referenciado": True,
        "muestra_pedida": True,
        "email_corporativo": False,
        "contacto_reciente": False,
    }
    score = lead_scoring.puntuar(señales)
    assert score == 75
    assert lead_scoring.prioridad_sugerida(score) == "alta"


def test_email_corporativo():
    assert lead_scoring.es_email_corporativo("compras@interiorismo-hd.es") is True
    assert lead_scoring.es_email_corporativo("juan@gmail.com") is False
    assert lead_scoring.es_email_corporativo("") is False
    assert lead_scoring.es_email_corporativo(None) is False
    assert lead_scoring.es_email_corporativo("sin-arroba") is False


def test_el_score_es_determinista():
    """Misma entrada, misma salida: no hay azar ni IA en el camino."""
    señales = {"muestra_pedida": True, "contacto_reciente": True}
    assert lead_scoring.puntuar(señales) == lead_scoring.puntuar(señales) == 45
