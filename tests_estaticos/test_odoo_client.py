"""El panel lee Odoo solo por su API (hallazgo 2.2 de la auditoría).

En la v1 el README decía "panel 100 % JSON-RPC" mientras panel_muebles.py
hacía 35 consultas SQL con usuario y contraseña fijos, y el cliente JSON-RPC
no lo llamaba nadie. Estas pruebas fijan lo contrario:
  - el panel no importa ningún driver de base de datos ni ejecuta SQL;
  - todas las lecturas pasan por odoo_client con dominios del ORM;
  - la API key no tiene valor por defecto y el panel escucha en loopback.
"""

from __future__ import annotations

import ast
import io
import json
import urllib.error
from datetime import date
from pathlib import Path

import pytest

PANEL = Path(__file__).resolve().parents[1] / "panel"


@pytest.fixture()
def cliente(cliente_odoo):
    return cliente_odoo


class OdooFalso:
    """Ejecutor en memoria: apunta cada llamada y responde lo preparado."""

    def __init__(self, respuestas=None):
        self.llamadas = []
        self.respuestas = respuestas or {}

    def __call__(self, modelo, metodo, **parametros):
        self.llamadas.append((modelo, metodo, parametros))
        respuesta = self.respuestas.get((modelo, metodo), 0 if metodo == "search_count" else [])
        return respuesta(parametros) if callable(respuesta) else respuesta


def test_el_panel_no_usa_sql_ni_drivers_de_base_de_datos():
    for fichero in ("panel_muebles.py", "odoo_client.py", "asistente.py"):
        codigo = (PANEL / fichero).read_text(encoding="utf-8")
        arbol = ast.parse(codigo)
        importados = {
            alias.name.split(".")[0]
            for nodo in ast.walk(arbol) if isinstance(nodo, (ast.Import, ast.ImportFrom))
            for alias in getattr(nodo, "names", [])
        } | {
            (nodo.module or "").split(".")[0]
            for nodo in ast.walk(arbol) if isinstance(nodo, ast.ImportFrom)
        }
        assert not importados & {"psycopg2", "psycopg", "sqlite3", "odoorpc"}, fichero
        assert ".execute(" not in codigo, f"{fichero}: no debe ejecutar SQL"
        assert 'password="odoo"' not in codigo, f"{fichero}: credencial fija"


def test_el_panel_escucha_en_loopback_por_defecto(configuracion, monkeypatch):
    monkeypatch.delenv("MUEBLES_PANEL_HOST", raising=False)
    assert configuracion.panel_host() == "127.0.0.1"
    codigo = (PANEL / "panel_muebles.py").read_text(encoding="utf-8")
    assert '"0.0.0.0"' not in codigo


def test_la_api_key_es_obligatoria(configuracion, monkeypatch):
    monkeypatch.delenv("MUEBLES_ODOO_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="MUEBLES_ODOO_API_KEY"):
        configuracion.odoo_api_key()


def test_los_recuentos_usan_dominios_del_orm(cliente):
    falso = OdooFalso({("sale.order", "search_count"): 12})
    cliente.usar(falso)
    assert cliente.pedidos_confirmados() == 12
    assert falso.llamadas == [("sale.order", "search_count", {"domain": [("state", "=", "sale")]})]


def test_pendientes_con_los_mismos_estados_que_publicaba_la_v1(cliente):
    falso = OdooFalso()
    cliente.usar(falso)
    cliente.entregas_pendientes()
    cliente.compras_pendientes()
    cliente.asientos_contables()
    dominios = [llamada[2]["domain"] for llamada in falso.llamadas]
    assert ("state", "in", ["assigned", "waiting", "confirmed"]) in dominios[0]
    assert ("picking_type_id.code", "=", "outgoing") in dominios[0]
    assert dominios[1] == [("state", "in", ["draft", "sent", "to approve"])]
    assert dominios[2] == [("state", "=", "posted")]


def test_valor_del_almacen_a_coste_estandar(cliente):
    quants = [{"product_id": [1, "Mesa"], "quantity": 3.0},
              {"product_id": [2, "Silla"], "quantity": 10.0},
              {"product_id": [1, "Mesa"], "quantity": 1.0}]
    falso = OdooFalso({
        ("stock.quant", "search_read"): quants,
        ("product.product", "search_read"): [{"id": 1, "standard_price": 200.0},
                                             {"id": 2, "standard_price": 25.5}],
    })
    cliente.usar(falso)
    assert cliente.valor_almacen() == 4 * 200.0 + 10 * 25.5


def test_todas_las_cifras_de_almacen_ignoran_cantidades_negativas(cliente):
    """Stock negativo es un error de datos: ni suma ni resta en ninguna cifra."""
    falso = OdooFalso({("stock.quant", "search_read"): []})
    cliente.usar(falso)
    cliente.existencias_catalogo()
    cliente.referencias_con_stock()
    cliente.valor_almacen()
    cliente.traza_existencias_movimientos()
    quants = [ll for ll in falso.llamadas if ll[0] == "stock.quant"]
    assert len(quants) == 4
    for _, _, parametros in quants:
        assert ("quantity", ">", 0) in parametros["domain"]


def test_las_lineas_de_servicio_no_cuentan_como_fuera_de_catalogo(cliente):
    falso = OdooFalso({("sale.order.line", "search_count"): 2})
    cliente.usar(falso)
    assert cliente.lineas_fuera_catalogo() == 2
    dominio = falso.llamadas[0][2]["domain"]
    assert ("product_id.type", "!=", "service") in dominio
    assert ("product_id.is_furniture", "=", False) in dominio


def test_presupuestos_viejos_a_partir_de_30_dias(cliente, monkeypatch):
    monkeypatch.setattr(cliente, "_hoy", lambda: date(2026, 11, 7))
    falso = OdooFalso({("sale.order", "search_read"): [
        {"date_order": "2026-10-08 09:00:00"},   # 30 días: viejo
        {"date_order": "2026-10-09 09:00:00"},   # 29 días: aún no
        {"date_order": "2026-09-01 09:00:00"},   # 67 días: viejo
    ]})
    cliente.usar(falso)
    assert cliente.presupuestos_viejos() == 2
    assert cliente.actividad_dias_max_presupuesto() == 67


def test_la_mejor_oportunidad_es_la_que_puntua_el_modulo(cliente):
    falso = OdooFalso({("crm.lead", "search_read"): [
        {"id": 7, "name": "Tienda pequeña", "x_score_kavana": 25, "x_prioridad_sugerida": "baja",
         "x_es_contrato": False, "x_proyecto_referenciado": False, "x_muestra_pedida": False,
         "x_email_corporativo": True, "x_contacto_reciente": True},
        {"id": 3, "name": "Hotel Valencia", "x_score_kavana": 75, "x_prioridad_sugerida": "alta",
         "x_es_contrato": True, "x_proyecto_referenciado": True, "x_muestra_pedida": True,
         "x_email_corporativo": False, "x_contacto_reciente": False},
    ]})
    cliente.usar(falso)
    mejor = cliente.mejor_oportunidad()
    assert mejor["nombre"] == "Hotel Valencia"
    assert mejor["score_kavana"] == 75
    assert mejor["senales"]["muestra_pedida"] is True
    campos = falso.llamadas[0][2]["fields"]
    assert "x_score_kavana" in campos, "el score se lee del módulo, no se recalcula"


def test_el_transporte_habla_json2_con_bearer(cliente, monkeypatch):
    capturado = {}

    class Respuesta(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def abrir(peticion, timeout):
        capturado["url"] = peticion.full_url
        capturado["cabeceras"] = dict(peticion.header_items())
        capturado["cuerpo"] = json.loads(peticion.data)
        return Respuesta(b"5")

    monkeypatch.setattr(cliente.urllib.request, "urlopen", abrir)
    api = cliente.OdooJson2("http://odoo:8069/", "furniture_db", "clave-de-prueba")
    assert api("res.partner", "search_count", domain=[["customer_rank", ">", 0]]) == 5
    assert capturado["url"] == "http://odoo:8069/json/2/res.partner/search_count"
    assert capturado["cabeceras"]["Authorization"] == "bearer clave-de-prueba"
    assert capturado["cabeceras"]["X-odoo-database"] == "furniture_db"
    assert capturado["cuerpo"] == {"domain": [["customer_rank", ">", 0]]}


def test_un_error_de_odoo_no_filtra_la_traza(cliente, monkeypatch):
    def abrir(peticion, timeout):
        cuerpo = json.dumps({"message": "Acceso denegado", "debug": "Traceback ..."}).encode()
        raise urllib.error.HTTPError(peticion.full_url, 403, "Forbidden", {}, io.BytesIO(cuerpo))

    monkeypatch.setattr(cliente.urllib.request, "urlopen", abrir)
    api = cliente.OdooJson2("http://odoo:8069", "furniture_db", "clave")
    with pytest.raises(cliente.OdooClientError) as error:
        api("crm.lead", "write", ids=[1], vals={"name": "x"})
    assert "HTTP 403 Acceso denegado" in str(error.value)
    assert "Traceback" not in str(error.value)
