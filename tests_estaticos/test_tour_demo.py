"""Recorrido guiado de la demo: el asset está declarado y no escribe en la base."""

from __future__ import annotations

import ast
import re


def _manifiesto(raiz) -> dict:
    return ast.literal_eval((raiz / "__manifest__.py").read_text(encoding="utf-8"))


def test_el_tour_esta_en_los_assets_del_backend(raiz):
    assets = _manifiesto(raiz)["assets"]["web.assets_backend"]
    assert "ODOO_CRM/static/src/js/tour_demo.js" in assets


def test_los_assets_declarados_existen(raiz):
    for lista in _manifiesto(raiz)["assets"].values():
        for ruta in lista:
            assert (raiz / ruta.removeprefix("ODOO_CRM/")).is_file(), ruta


def test_el_tour_registra_pasos_y_el_menu_de_usuario(raiz):
    js = (raiz / "static/src/js/tour_demo.js").read_text(encoding="utf-8")
    assert 'registry.category("web_tour.tours").add(TOUR' in js
    assert 'registry.category("user_menuitems").add("muebles_tour"' in js
    pasos = re.findall(r"trigger:", js)
    assert 4 <= len(pasos) <= 8


def test_el_tour_no_activa_el_onboarding_del_servidor(raiz):
    js = (raiz / "static/src/js/tour_demo.js").read_text(encoding="utf-8")
    # Antes de lanzar el tour se marca toursEnabled en el cliente; si no, el
    # motor de Odoo escribe tour_enabled en el usuario y encadena sus tours.
    assert js.index("toursEnabled = true") < js.index("startTour(")
    assert "switch_tour_enabled" not in js
