"""El verificador del laboratorio: los 14 recuentos del estado inicial.

Comprueba el manifiesto sin conectarse a ninguna base: que las claves cuadran
entre sí y que los números esperados son coherentes entre ellos.
"""

from __future__ import annotations

COMPROBACIONES = 14


def test_manifiesto_y_esperado_hablan_de_lo_mismo(verificador):
    assert set(verificador.MANIFIESTO) == set(verificador.ESPERADO)


def test_numero_de_comprobaciones(verificador):
    assert len(verificador.MANIFIESTO) == COMPROBACIONES


def test_cada_comprobacion_tiene_su_consulta(verificador):
    for nombre, consulta in verificador.MANIFIESTO.items():
        assert isinstance(consulta, str) and consulta.strip(), nombre
        assert "select" in consulta.lower(), nombre


def test_los_tres_catalogos_cuentan_lo_mismo(verificador):
    esperado = verificador.ESPERADO
    assert esperado["productos activos"] == esperado["productos publicados"]
    assert esperado["productos publicados"] == esperado["referencias del modelo propio"]


def test_los_pedidos_cuadran_con_sus_estados(verificador):
    esperado = verificador.ESPERADO
    assert esperado["pedidos confirmados"] + esperado["presupuestos"] == esperado["pedidos de venta"]


def test_los_albaranes_hechos_no_superan_el_total(verificador):
    esperado = verificador.ESPERADO
    assert esperado["albaranes hechos"] <= esperado["albaranes"]


def test_el_almacen_arranca_con_genero(verificador):
    assert verificador.ESPERADO["unidades en almacén"] > 0


def test_la_banda_de_demo_esta_declarada(verificador):
    assert "demostración" in verificador.BANNER.lower()
