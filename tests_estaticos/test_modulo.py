"""El módulo de Odoo: manifiesto, vistas, permisos y controlador.

Nada de esto necesita un servidor: se comprueba que el módulo está bien
formado y que lo que declara existe de verdad en el repositorio.
"""

from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET

DEPENDENCIAS = {
    "base", "mail", "product", "stock", "account", "sale_management", "website",
    "website_sale", "crm", "purchase", "contacts",
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


def test_version_para_odoo_20(raiz):
    assert _manifiesto(raiz)["version"].startswith("20.0.")


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


def test_la_ficha_de_mobiliario_hereda_el_producto_nativo(raiz):
    """Sin catálogo paralelo: las vistas amplían la ficha nativa de producto."""
    assert not (raiz / "views" / "furniture_product_views.xml").exists()
    contenido = (raiz / "views" / "product_template_views.xml").read_text(encoding="utf-8")
    assert 'ref="product.product_template_form_view"' in contenido
    assert 'name="res_model">product.template' in contenido
    for campo in ("furniture_material", "furniture_dimensions", "furniture_style",
                  "furniture_warranty_months"):
        assert f'name="{campo}"' in contenido, f"la vista no muestra {campo}"


def test_la_plantilla_del_panel_cuelga_del_sitio(raiz):
    contenido = (raiz / "views" / "panel_template.xml").read_text(encoding="utf-8")
    assert 't-call="website.layout"' in contenido
    for variable in ("total_products", "furniture_products", "customers", "orders"):
        assert variable in contenido, f"la plantilla no pinta {variable}"


def test_permisos_del_usuario_de_integracion(raiz):
    """Permisos en el formato de Odoo 20 (ir.access + operation CRUD).

    En Odoo 20 los permisos viven en `security/ir.access.csv`: el modelo se
    deduce del NOMBRE del fichero y las operaciones son códigos CRUD. El grupo
    del panel solo lee (`r`): nunca crea, modifica ni borra.
    """
    filas = (raiz / "security" / "ir.access.csv").read_text(encoding="utf-8").strip().splitlines()
    cabecera = filas[0].split(",")
    assert cabecera == ["id", "name", "model_id", "group_id/id", "operation", "domain"]
    cuerpo = [fila.split(",") for fila in filas[1:]]
    assert cuerpo, "el grupo del panel necesita permisos de lectura"
    for fila in cuerpo:
        assert fila[3] == "group_panel_lectura", fila
        assert fila[4] == "r", f"{fila[2]}: el grupo del panel solo puede leer"
    modelos = {fila[2] for fila in cuerpo}
    assert {"crm.lead", "sale.order", "stock.quant", "product.template"} <= modelos
    assert "furniture.product" not in modelos


def test_el_fichero_de_permisos_no_usa_el_nombre_antiguo(raiz):
    """El nombre del fichero decide el modelo que Odoo carga al importar."""
    assert not (raiz / "security" / "ir.model.access.csv").exists(), (
        "en Odoo 20 el fichero debe llamarse ir.access.csv: con el nombre "
        "antiguo Odoo busca el modelo inexistente ir.model.access"
    )



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


def test_la_ficha_de_mobiliario_amplia_product_template(raiz):
    fuentes = "\n".join(ruta.read_text(encoding="utf-8") for ruta in (raiz / "models").glob("*.py"))
    assert "_name = 'furniture.product'" not in fuentes, "no debe volver el catálogo paralelo"
    codigo = (raiz / "models" / "product_template.py").read_text(encoding="utf-8")
    assert "_inherit = 'product.template'" in codigo
    for campo in ("furniture_material", "furniture_dimensions", "furniture_style",
                  "furniture_warranty_months", "is_furniture"):
        assert re.search(rf"\b{campo}\s*=\s*fields\.", codigo), f"falta {campo}"
    # precio, coste y stock son los nativos: el módulo no los redefine
    for nativo in ("list_price", "standard_price", "qty_available"):
        assert not re.search(rf"\b{nativo}\s*=\s*fields\.", codigo), nativo


def test_hay_migracion_de_datos_desde_la_v1(raiz):
    version = _manifiesto(raiz)["version"]
    carpeta = raiz / "migrations" / version
    assert (carpeta / "pre-migrate.py").exists()
    assert (carpeta / "post-migrate.py").exists()
    pre = (carpeta / "pre-migrate.py").read_text(encoding="utf-8")
    assert "furniture_product_v1_backup" in pre, "la tabla v1 se conserva como copia"


def test_los_campos_calculados_declaran_dependencias(raiz):
    """Sin @api.depends la caché del ORM no se invalida (hallazgo de la auditoría)."""
    for fichero in ("crm_lead_scoring.py", "product_template.py"):
        codigo = (raiz / "models" / fichero).read_text(encoding="utf-8")
        computes = set(re.findall(r"compute='(_compute_\w+)'", codigo))
        for metodo in computes:
            assert re.search(rf"@api\.depends\([^)]*\)\s*\n\s*def {metodo}\(", codigo), (
                f"{fichero}: {metodo} sin @api.depends")


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
    assert 'inherit_id" ref="crm.crm_case_tree_view_oppor"' in contenido
    for campo in ("x_score_kavana", "x_prioridad_sugerida", "x_es_contrato", "x_muestra_pedida"):
        assert f'name="{campo}"' in contenido, f"la vista no pinta {campo}"


def test_el_manifiesto_carga_las_vistas_de_scoring(raiz):
    assert "views/crm_lead_scoring_views.xml" in _manifiesto(raiz)["data"]
