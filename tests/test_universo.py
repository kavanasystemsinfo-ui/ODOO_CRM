"""El universo versionado (data/universo.json) no deriva de la realidad del repo.

Cruza el universo con las fuentes reales: los recuentos canónicos del
restaurador, el catálogo CSV y los scripts de poblado. Si alguien toca una
fuente sin actualizar el universo (o al revés), este test lo canta.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _universo() -> dict:
    return json.loads((RAIZ / "data" / "universo.json").read_text(encoding="utf-8"))


def test_el_universo_declara_los_recuentos_canonicos_del_restaurador():
    codigo = (RAIZ / "panel" / "demo_restaurar_muebles.py").read_text(encoding="utf-8")
    cuerpo = re.search(r"ESPERADO = \{(.*?)\n\}", codigo, re.S).group(1)
    esperado_restaurador = dict(re.findall(r'"([^"]+)":\s*(\d+)', cuerpo))
    universo = _universo()["recuentos_canonicos"]
    for nombre, valor in esperado_restaurador.items():
        assert nombre in universo, f"el universo no declara «{nombre}»"
        assert universo[nombre] == int(valor), (
            f"«{nombre}»: universo dice {universo[nombre]}, restaurador dice {valor}"
        )


def test_el_universo_cuadra_con_el_catalogo_csv():
    with (RAIZ / "data" / "furniture.product.csv").open(encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    universo = _universo()["catalogo"]
    assert universo["referencias"] == len(filas)
    assert sorted(universo["categorias"]) == sorted({f["category"] for f in filas})
    assert sorted(universo["materiales"]) == sorted({f["material"] for f in filas})
    assert sorted(universo["estilos"]) == sorted({f["style"] for f in filas})
    garantias = {int(f["warranty_months"]) for f in filas}
    assert universo["garantia_meses"] in garantias


def test_el_orden_de_poblado_apunta_a_scripts_reales():
    universo = _universo()["poblado"]["orden"]
    for paso in universo:
        assert (RAIZ / "scripts" / paso).exists(), f"el universo referencia un script que no existe: {paso}"


def test_la_empresa_del_universo_es_la_de_create_lab_data():
    codigo = (RAIZ / "scripts" / "create_lab_data.py").read_text(encoding="utf-8")
    empresa = _universo()["empresa"]
    for campo in ("nombre", "direccion", "ciudad", "codigo_postal", "telefono", "email", "web"):
        valor = empresa[campo]
        assert valor in codigo, f"el universo declara {campo}={valor} y create_lab_data.py no lo tiene"
