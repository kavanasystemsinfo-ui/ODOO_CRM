"""Reglas de datos coherentes de la empresa simulada (sin Odoo)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def datos():
    spec = importlib.util.spec_from_file_location("simulador_datos", RAIZ / "models" / "simulador_datos.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize("nombre, ciudad", [
    ("Espai Llar Barcelona S.L.", "Barcelona"), ("Contract Habitat Madrid S.L.", "Madrid"),
    ("Mobiliari Urba Valencia S.L.", "València"), ("Interiors Vinalopó S.L.", "Elda"),
    ("Decoracio i Contract Alacant S.L.", "Alacant"), ("Mobiliario Contract Sur S.L.", "Sevilla"),
    ("Disseny Interior Maestrat S.L.", "Vinaròs"), ("Fusta i Disseny Segorbe S.L.", "Segorbe"),
    ("Moble i Decoració Alzira S.L.", "Alzira"), ("Disseny Moble Castelló", "Castelló de la Plana"),
])
def test_la_ciudad_casa_con_el_nombre(datos, nombre, ciudad):
    assert datos.ciudad_para(nombre, "x") == ciudad


def test_la_direccion_es_coherente_y_estable(datos):
    d = datos.direccion("Interiors Vinalopó S.L.", "res.partner/22")
    assert d == datos.direccion("Interiors Vinalopó S.L.", "res.partner/22")
    provincia, cp, prefijo = datos.CIUDADES[d["city"]]
    assert d["provincia"] == provincia and d["zip"].startswith(cp) and len(d["zip"]) == 5
    assert d["phone"].replace(" ", "").startswith("+34" + prefijo)
    assert re.fullmatch(r"\+34 \d{3} \d{3} \d{3}", d["phone"])


def test_nif_y_cif_validos(datos):
    for semilla in ("a", "b", "res.partner/11", "res.partner/41"):
        cif = datos.cif(semilla)
        assert datos.cif_valido(cif), cif
        assert cif.startswith("ESB")
        nif = datos.nif(semilla)
        assert nif.startswith("ES") and nif[-1] == datos.LETRAS_NIF[int(nif[2:10]) % 23]
    assert datos.cif_valido("B12345674")       # CIF de ejemplo con control correcto
    assert not datos.cif_valido("B12345678")   # el de la empresa de ejemplo no lo es
    assert not datos.cif_valido("US12345673")


def test_telefonos(datos):
    assert datos.es_telefono_espanol("+34 964 123 456")
    for extranjero in ("+32 10 588 558", "(623)-853-7197", "+1 312 349 2324", "+58 212 681 0538"):
        assert not datos.es_telefono_espanol(extranjero)
    assert datos.movil("x").startswith("+34 6")


def test_empresa_y_textos(datos):
    assert datos.empresa_del_titulo("Presupuesto de 25 mesas de comedor — Contract Habitat") == "Contract Habitat"
    assert datos.empresa_del_titulo("Mesa de comedor a medida") == ""
    assert datos.renombrar("Trelian: nuevas oficinas") == "Grupo Trelles: nuevas oficinas"
    assert datos.parece_empresa("Moble Tradicional Alacant S.L.")
    assert datos.parece_empresa("Constructora Alzira")
    assert not datos.parece_empresa("Laura Ferrer")
    assert datos.parece_ingles("[x] Tufted Gallery Bench Werner BR\nAdd a touch of sophistication with the")
    assert not datos.parece_ingles("[x] Banco capitoné Werner BR\nBanco de estilo clásico tapizado.")
    assert not datos.parece_ingles("[console-table-umber] Consola Umber\nConsola de estilo art déco.")
    assert datos.telefono_de_relleno("+34 600 007 007")
    assert not datos.telefono_de_relleno("+34 964 213 884")


@pytest.mark.parametrize("nombre, sustantivo, participio", [
    ("Mesa auxiliar Daxon", "Mesa", "fabricada"), ("Sillón auxiliar Kalani", "Sillón", "fabricado"),
    ("Taburete de barra tapizado Bala", "Taburete", "fabricado"),
    ("Mesas nido Holden", "Mesas nido", "fabricadas"),
    ("Mesita de noche de chapa Uma", "Mesita de noche", "fabricada"),
    ("Chaise longue Moda", "Chaise longue", "fabricada"),
    ("Juego de mesitas auxiliares Hade G", "Juego de mesitas", "fabricado"),
    ("Vinoteca Bliss", "Vinoteca", "fabricada"), ("Espejo Musa L", "Espejo", "fabricado"),
])
def test_sustantivo_y_concordancia(datos, nombre, sustantivo, participio):
    texto, _ = datos.corregir_descripcion(
        nombre, "Silla de estilo moderno fabricado en madera. Garantía de 24 meses.")
    assert texto == f"{sustantivo} de estilo moderno {participio} en madera. Garantía de 24 meses."


def test_el_material_del_nombre_manda(datos):
    texto, material = datos.corregir_descripcion(
        "Mesita auxiliar de mármol Knox", "Mesa de estilo moderno fabricado en travertino. Garantía de 24 meses.")
    assert material == "mármol" and "fabricada en mármol" in texto
    assert datos.corregir_descripcion("Banco Anna", "Texto libre sin plantilla.") == ("Texto libre sin plantilla.", None)


def test_todo_el_catalogo_concuerda(datos, catalogo):
    for fila in catalogo:
        texto, material = datos.corregir_descripcion(fila["name"], fila["description"])
        assert texto == fila["description"], fila["name"]
        assert material is None, fila["name"]
