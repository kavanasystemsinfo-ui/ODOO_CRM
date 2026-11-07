"""El catálogo: 80 muebles con datos coherentes y en español.

Es el dato del que cuelgan los tres catálogos del laboratorio (modelo propio,
productos estándar y tienda), así que aquí se comprueba que no se descuadre.
"""

from __future__ import annotations

import pytest

# Cabecera esperada del CSV del catálogo.
COLUMNAS_CSV = (
    "id", "name", "category", "list_price", "standard_price", "qty_available",
    "material", "dimensions", "style", "warranty_months", "description",
)

# Reparto real del estado inicial (medido antes de publicar el laboratorio).
REPARTO_CATEGORIAS = {
    "mesas": 34, "sillas": 14, "otros": 8, "armarios": 8, "bancos": 6,
    "sofas": 4, "mesitas": 3, "butacas": 2, "camas": 1,
}
ESTILOS = {"Antiguo", "Clásico", "Contemporáneo", "Minimalista", "Moderno", "Vintage"}
TOTAL = 80


def test_catalogo_tiene_80_muebles(catalogo):
    assert len(catalogo) == TOTAL


def test_cabecera_del_csv(catalogo):
    assert tuple(catalogo[0].keys()) == COLUMNAS_CSV


def test_ids_correlativos_y_unicos(catalogo):
    esperados = [f"furniture_product_{n:03d}" for n in range(1, TOTAL + 1)]
    assert [fila["id"] for fila in catalogo] == esperados


@pytest.mark.parametrize("columna", ["name", "category", "material", "style", "description"])
def test_columnas_de_texto_sin_vacios(catalogo, columna):
    vacios = [fila["id"] for fila in catalogo if not fila[columna].strip()]
    assert vacios == []


def test_nombres_unicos(catalogo):
    nombres = [fila["name"] for fila in catalogo]
    assert len(set(nombres)) == TOTAL


def test_reparto_por_categoria(catalogo):
    reparto: dict[str, int] = {}
    for fila in catalogo:
        reparto[fila["category"]] = reparto.get(fila["category"], 0) + 1
    assert reparto == REPARTO_CATEGORIAS


def test_estilos_del_catalogo(catalogo):
    assert {fila["style"] for fila in catalogo} == ESTILOS


def test_precios_coherentes(catalogo):
    for fila in catalogo:
        pvp = float(fila["list_price"])
        coste = float(fila["standard_price"])
        assert pvp > 0, fila["id"]
        assert coste > 0, fila["id"]
        assert coste < pvp, f"{fila['id']} vende por debajo del coste"


def test_margen_razonable(catalogo):
    for fila in catalogo:
        proporcion = float(fila["standard_price"]) / float(fila["list_price"])
        assert 0.2 <= proporcion <= 0.9, f"{fila['id']}: coste {proporcion:.0%} del PVP"


def test_existencias_enteras_y_no_negativas(catalogo):
    for fila in catalogo:
        cantidad = float(fila["qty_available"])
        assert cantidad >= 0, fila["id"]
        assert cantidad == int(cantidad), fila["id"]


def test_garantia_de_24_meses_en_todos(catalogo):
    assert {fila["warranty_months"] for fila in catalogo} == {"24"}


def test_descripciones_en_espanol_y_con_garantia(catalogo):
    for fila in catalogo:
        texto = fila["description"]
        assert "Garantía" in texto, fila["id"]
        assert not any(palabra in texto.lower() for palabra in (" the ", " and ", " warranty")), fila["id"]


def test_descripciones_no_copiadas_una_a_una(catalogo):
    # Hay 80 fichas y 42 textos distintos: repetir texto es legítimo (mismo
    # material y estilo), pero no que todas sean la misma frase.
    assert len({fila["description"] for fila in catalogo}) >= 30


def test_dimensiones_o_vacio(catalogo):
    # La columna existe en el modelo; en el estado inicial está sin rellenar,
    # así que solo se exige que no traiga basura.
    for fila in catalogo:
        assert fila["dimensions"].strip() in ("", ) or "x" in fila["dimensions"].lower(), fila["id"]
