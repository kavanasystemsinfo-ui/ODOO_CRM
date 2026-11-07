"""El asistente técnico: busca en los documentos reales y no inventa nada.

Sin clave de modelo (el caso de CI), tiene que devolver los fragmentos exactos
del repositorio y declarar de dónde sale el texto.
"""

from __future__ import annotations

import uuid

import pytest


def test_encuentra_fragmentos_del_repositorio(asistente):
    fragmentos = asistente.buscar("¿cómo se comprueba que el almacén cuadra con el libro?")
    assert fragmentos, "no encuentra nada sobre el almacén"
    assert all(f["fichero"] and f["texto"] for f in fragmentos)


def test_las_fuentes_son_ficheros_del_proyecto(asistente):
    fuentes = [f["fichero"] for f in asistente.buscar("tests del catálogo con pytest")]
    assert fuentes
    for fichero in fuentes:
        assert fichero.endswith((".md", ".py", ".xml", ".csv", ".ini", ".txt", ".json")), fichero
        assert not fichero.startswith(("landing/", "video/")), fichero


def test_pregunta_sin_terminos_no_devuelve_nada(asistente):
    assert asistente.buscar("de la y el") == []


def test_pregunta_muy_corta_lo_dice(asistente):
    salida = asistente.responder("ok")
    assert salida["origen"] == "vacio"
    assert salida["respuesta"]


def test_pregunta_fuera_del_proyecto_lo_dice(asistente):
    # Cadena aleatoria: no puede estar en ningún documento del repositorio.
    salida = asistente.responder(uuid.uuid4().hex)
    assert salida["origen"] == "sin-fragmentos"
    assert salida["fuentes"] == []


def test_sin_clave_de_modelo_devuelve_los_fragmentos(asistente, monkeypatch):
    monkeypatch.setattr(asistente, "_clave", lambda: "")
    salida = asistente.responder("¿cómo se comprueba que el almacén cuadra con el libro?")
    assert salida["origen"] == "sin-clave"
    assert salida["fuentes"], "debería citar de dónde sale"
    assert "sin clave" in salida["respuesta"].lower()
    assert len(salida["respuesta"]) > 80


def test_el_instruccion_prohibe_inventar(asistente):
    assert "no está en los fragmentos" in asistente.INSTRUCCIONES
    assert "español" in asistente.INSTRUCCIONES


def test_los_documentos_pesados_quedan_fuera(asistente):
    rutas = {fichero for fichero, _, _ in asistente._fragmentos()}
    assert rutas, "no ha encontrado documentos"
    for ruta in rutas:
        assert not ruta.endswith("districthome_products.json")
        assert not ruta.endswith(".gz")


@pytest.mark.parametrize("pregunta,esperado", [
    ("¿cuántas pruebas tiene la suite?", "tests"),
    ("¿con qué se hace la búsqueda del asistente?", "asistente"),
])
def test_la_busqueda_prioriza_el_fichero_adecuado(asistente, pregunta, esperado):
    fuentes = [f["fichero"] for f in asistente.buscar(pregunta)]
    assert any(esperado in fuente for fuente in fuentes), fuentes
