"""El módulo de Odoo: manifiesto, vistas, permisos y controlador.

Nada de esto necesita un servidor: se comprueba que el módulo está bien
formado y que lo que declara existe de verdad en el repositorio.
"""

from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET

DEPENDENCIAS = {
    "base", "product", "stock", "sale_management", "website", "crm", "purchase", "contacts",
}


def _manifiesto(raiz) -> dict:
    return ast.literal_eval((raiz / "__manifest__.py").read_text(encoding="utf-8"))


def test_manifiesto_con_las_claves_obligatorias(raiz):
    manifiesto = _manifiesto(raiz)
    for clave in ("name", "version", "author", "license", "depends", "data"):
        assert manifiesto.get(clave), f"falta {clave}"
    assert manifiesto["author"] == "Kavana Systems"
    assert manifiesto["license"] == "LGPL-3"
    assert manifiesto["installable"] is True


def test_version_para_odoo_17(raiz):
    assert _manifiesto(raiz)["version"].startswith("17.0.")


def test_dependencias_del_modulo(raiz):
    assert DEPENDENCIAS.issubset(set(_manifiesto(raiz)["depends"]))


def test_los_ficheros_declarados_existen(raiz):
    faltan = [ruta for ruta in _manifiesto(raiz)["data"] if not (raiz / ruta).exists()]
    assert faltan == []


def test_las_vistas_son_xml_valido(raiz):
    for ruta in (raiz / "views").glob("*.xml"):
        ET.parse(ruta)


def test_las_vistas_siguen_las_convenciones_oca(raiz):
    """Convenciones que exige el linter oficial OCA (oca-checks-odoo-module)."""
    for ruta in (raiz / "views").glob("*.xml"):
        contenido = ruta.read_text(encoding="utf-8")
        assert contenido.startswith('<?xml version="1.0" encoding="UTF-8" ?>'), (
            f"{ruta.name}: cabecera XML canónica OCA"
        )
        assert "<data>" not in contenido, f"{ruta.name}: nodo <data> deprecado, los records van bajo <odoo>"
        assert "<tree string=" not in contenido, f"{ruta.name}: atributo string deprecado en <tree>"
        assert "t-esc=" not in contenido, f"{ruta.name}: t-esc deprecado desde Odoo 15, usar t-out"


def test_la_vista_del_catalogo_usa_el_modelo_propio(raiz):
    contenido = (raiz / "views" / "furniture_product_views.xml").read_text(encoding="utf-8")
    assert contenido.count('name="model">furniture.product') >= 3  # lista, formulario y búsqueda
    for campo in ("category", "list_price", "standard_price", "material", "style", "warranty_months"):
        assert f'name="{campo}"' in contenido, f"la vista no muestra {campo}"


def test_la_plantilla_del_panel_cuelga_del_sitio(raiz):
    contenido = (raiz / "views" / "panel_template.xml").read_text(encoding="utf-8")
    assert 't-call="website.layout"' in contenido
    for variable in ("total_products", "furniture_products", "customers", "orders"):
        assert variable in contenido, f"la plantilla no pinta {variable}"


def test_permisos_del_modelo(raiz):
    filas = (raiz / "security" / "ir.model.access.csv").read_text(encoding="utf-8").strip().splitlines()
    cabecera = filas[0].split(",")
    assert cabecera == [
        "id", "name", "model_id:id", "group_id:id",
        "perm_read", "perm_write", "perm_create", "perm_unlink",
    ]
    cuerpo = filas[1]
    assert "model_furniture_product" in cuerpo
    assert "base.group_user" in cuerpo
    assert cuerpo.endswith("1,1,1,1"), "los usuarios internos deben poder leer y escribir el catálogo"


def test_el_modulo_carga_modelos_y_controladores(raiz):
    contenido = (raiz / "__init__.py").read_text(encoding="utf-8")
    assert "from . import models" in contenido
    assert "from . import controllers" in contenido


def test_controlador_del_panel(raiz):
    codigo = (raiz / "controllers" / "main.py").read_text(encoding="utf-8")
    ast.parse(codigo)  # sintaxis válida
    assert "'/muebles/panel'" in codigo
    assert "auth='user'" in codigo, "el panel del módulo debe exigir sesión"
    assert "ODOO_CRM.panel_template" in codigo
    for variable in ("total_products", "furniture_products", "customers", "orders"):
        assert variable in codigo


def test_el_modelo_declara_los_campos_del_catalogo(raiz):
    fuentes = "\n".join(ruta.read_text(encoding="utf-8") for ruta in (raiz / "models").glob("*.py"))
    assert "_name = 'furniture.product'" in fuentes
    for campo in ("name", "category", "list_price", "standard_price", "qty_available",
                  "material", "dimensions", "style", "warranty_months", "description"):
        assert re.search(rf"\b{campo}\s*=\s*fields\.", fuentes), f"el modelo no declara {campo}"


def test_hereda_crm_lead_con_scoring_determinista(raiz):
    """El módulo hereda crm.lead con las señales y el score del benchmark."""
    codigo = (raiz / "models" / "crm_lead_scoring.py").read_text(encoding="utf-8")
    ast.parse(codigo)
    assert "_inherit = 'crm.lead'" in codigo
    for campo in ("x_es_contrato", "x_proyecto_referenciado", "x_muestra_pedida",
                  "x_contacto_reciente", "x_email_corporativo", "x_score_kavana",
                  "x_prioridad_sugerida"):
        assert re.search(rf"\b{campo}\s*=\s*fields\.", codigo), f"falta el campo {campo}"
    # el score no se guarda: se recalcula al leer (patrón del benchmark)
    assert "compute='_compute_x_score_kavana'" in codigo
    assert "store=True" not in codigo


def test_las_vistas_de_scoring_son_xml_valido_y_heredan_del_crm(raiz):
    ruta = raiz / "views" / "crm_lead_scoring_views.xml"
    ET.parse(ruta)
    contenido = ruta.read_text(encoding="utf-8")
    assert 'inherit_id" ref="crm.crm_lead_view_form"' in contenido
    assert 'inherit_id" ref="crm.crm_lead_view_tree"' in contenido
    for campo in ("x_score_kavana", "x_prioridad_sugerida", "x_es_contrato", "x_muestra_pedida"):
        assert f'name="{campo}"' in contenido, f"la vista no pinta {campo}"


def test_el_manifiesto_carga_las_vistas_de_scoring(raiz):
    assert "views/crm_lead_scoring_views.xml" in _manifiesto(raiz)["data"]
