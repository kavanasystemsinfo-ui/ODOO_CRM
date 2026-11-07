"""La lógica del panel del día: formato español y frases deterministas.

El panel no escribe en el laboratorio y sus frases son reglas, no IA, así que se
pueden comprobar sin base de datos.
"""

from __future__ import annotations

import importlib

import pytest

CIFRAS = {
    "productos": 80,
    "unidades": 2190,
    "referencias": 80,
    "valor_almacen": 12415.5,
    "entregas_hechas": 33,
    "entregas_pendientes": 4,
    "recepciones_hechas": 8,
    "recepciones_pendientes": 3,
    "pedidos": 56,
    "confirmados": 37,
    "presupuestos": 19,
    "actividades": 30,
    "vencidas": 3,
    "hoy": 5,
    "manana": 2,
    "proximas": 20,
    "salud_dato": [{"campo": "almacén cuadrado", "ok": True}],
}


@pytest.mark.parametrize("valor,esperado", [
    (12415, "12.415"),
    (80, "80"),
    (0, "0"),
])
def test_formato_numero_espanol_enteros(panel, valor, esperado):
    assert panel.formato_numero(valor) == esperado


def test_formato_numero_espanol_decimales(panel):
    assert panel.formato_numero(12415.5) == "12.415,50"


@pytest.mark.parametrize("parte,total,esperado", [
    (1, 3, "33,3 %"),
    (41, 48, "85,4 %"),
    (0, 0, "0,0 %"),
])
def test_porcentaje_en_formato_espanol(panel, parte, total, esperado):
    assert panel._porcentaje(parte, total) == esperado


def test_resumen_cuenta_lo_que_ha_pasado_hoy(panel):
    resumen = panel.construir_resumen(dict(CIFRAS))
    texto = " ".join(resumen["frases"])
    assert "80 muebles publicados" in texto
    assert "2.190 unidades" in texto
    assert "12.415,50 €" in texto
    assert "33 entregas hechas" in texto
    assert "3 pendientes de recibir" in texto
    assert "37 están confirmados" in texto


def test_resumen_declara_la_ia_precomputada(panel):
    resumen = panel.construir_resumen(dict(CIFRAS))
    assert resumen["ia"], "el panel debe declarar de dónde sale el texto"
    assert "sin clave" in resumen["ia"][0]


def test_resumen_sin_problemas_de_dato_no_se_queja(panel):
    texto = " ".join(panel.construir_resumen(dict(CIFRAS))["frases"])
    assert "no puedo afirmar nada" not in texto


def test_resumen_con_dato_roto_lo_dice(panel):
    cifras = dict(CIFRAS)
    cifras["salud_dato"] = [{"campo": "almacén cuadrado", "ok": False}]
    texto = " ".join(panel.construir_resumen(cifras)["frases"])
    assert "almacén cuadrado" in texto
    assert "no puedo afirmar nada" in texto


def test_resumen_ignora_lo_que_no_aplica(panel):
    cifras = dict(CIFRAS)
    cifras["salud_dato"] = [{"campo": "valoración de existencias", "ok": False, "no_aplica": True}]
    texto = " ".join(panel.construir_resumen(cifras)["frases"])
    assert "no puedo afirmar nada" not in texto


def test_resumen_avisa_de_presupuestos_parados(panel):
    cifras = dict(CIFRAS, presupuestos_viejos=4, dias_presupuesto_viejo=7)
    texto = " ".join(panel.construir_resumen(cifras)["frases"])
    assert "4 presupuestos con más de 7 días" in texto


def test_configuracion_del_laboratorio_por_defecto(configuracion):
    assert configuracion.base_de_datos() == "furniture_db"
    assert configuracion.contenedor_bd() == "furniture_db"
    assert configuracion.contenedor_odoo() == "furniture_odoo"
    assert configuracion.puerto_panel() == 8081
    assert configuracion.puerto_odoo_host() == 8070
    assert configuracion.espera_minima_reinicio() == 180
    assert configuracion.snapshot().name == "snapshot_muebles_demo_canonico.sql.gz"


def test_configuracion_se_puede_apuntar_a_otro_laboratorio(configuracion, monkeypatch):
    monkeypatch.setenv("MUEBLES_DB", "otra_base")
    monkeypatch.setenv("MUEBLES_PANEL_PORT", "9999")
    recargado = importlib.reload(configuracion)
    try:
        assert recargado.base_de_datos() == "otra_base"
        assert recargado.puerto_panel() == 9999
    finally:
        monkeypatch.undo()
        importlib.reload(configuracion)


# ---------------------------------------------------------------------------
# Comparación de periodos (patrón mis-builder: hoy vs ayer y vs hace 7 días)
# ---------------------------------------------------------------------------

def test_frase_de_evolucion_sin_cambios(panel):
    frase = panel.frase_evolucion("entregas", 33, 33, 33)
    assert frase == "entregas: sin cambios frente a ayer ni a la semana pasada."


def test_frase_de_evolucion_sube(panel):
    frase = panel.frase_evolucion("entregas", 33, 28, 20)
    assert "ayer" in frase and "sube" in frase
    assert "5" in frase  # +5 frente a ayer


def test_frase_de_evolucion_baja(panel):
    frase = panel.frase_evolucion("entregas", 20, 33, 40)
    assert "baja" in frase
    assert "13" in frase  # -13 frente a ayer


def test_frase_de_evolucion_con_cero_como_referencia(panel):
    """De 0 a N es apertura, no crecimiento porcentual: se dice sin porcentaje."""
    frase = panel.frase_evolucion("entregas", 3, 0, 0)
    assert "3" in frase
    assert "%" not in frase


def test_resumen_incluye_la_evolucion_cuando_hay_datos(panel):
    cifras = dict(CIFRAS)
    cifras["evolucion"] = {
        "entregas_hoy": 33, "entregas_ayer": 28, "entregas_semana": 120,
        "recepciones_hoy": 8, "recepciones_ayer": 0, "recepciones_semana": 30,
    }
    resumen = panel.construir_resumen(cifras)
    texto = " ".join(resumen["frases"])
    assert "ayer" in texto or "semana" in texto
    # y las cifras de evolución viajan para que el HTML las pinte
    assert resumen["evolucion"] == cifras["evolucion"]


def test_resumen_sin_datos_de_evolucion_no_menciona_periodos(panel):
    texto = " ".join(panel.construir_resumen(dict(CIFRAS))["frases"])
    assert "ayer" not in texto

