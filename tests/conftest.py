"""Fixtures compartidas de la suite del laboratorio de muebles.

La suite se divide en dos:
  - estática: comprueba el módulo, el catálogo y la lógica del panel sin
    necesitar Odoo ni PostgreSQL (es la que corre en CI);
  - viva: comprueba el laboratorio en marcha y se salta sola si no se pide
    con la variable `MUEBLES_LAB=1`.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
PANEL = RAIZ / "panel"
CSV_CATALOGO = RAIZ / "data" / "furniture.product.csv"

COLUMNAS_CSV = (
    "id", "name", "category", "list_price", "standard_price", "qty_available",
    "material", "dimensions", "style", "warranty_months", "description",
)


@pytest.fixture(scope="session")
def raiz() -> Path:
    return RAIZ


@pytest.fixture(scope="session")
def catalogo() -> list[dict]:
    with CSV_CATALOGO.open(newline="", encoding="utf-8") as fichero:
        return list(csv.DictReader(fichero))


def _cargar(nombre: str, ruta: Path):
    """Carga un módulo por ruta (los scripts del panel no son paquetes)."""
    if str(ruta.parent) not in sys.path:
        sys.path.insert(0, str(ruta.parent))
    if nombre in sys.modules:
        return sys.modules[nombre]
    especificacion = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules[nombre] = modulo
    especificacion.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="session")
def panel():
    return _cargar("panel_muebles", PANEL / "panel_muebles.py")


@pytest.fixture(scope="session")
def verificador():
    return _cargar("demo_restaurar_muebles", PANEL / "demo_restaurar_muebles.py")


@pytest.fixture(scope="session")
def configuracion():
    return _cargar("configuracion", PANEL / "configuracion.py")
