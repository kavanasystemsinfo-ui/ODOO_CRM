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


# --- Límites y secretos del asistente público (fase 1) ---

def test_el_asistente_no_lee_claves_de_rutas_personales(raiz):
    codigo = (raiz / "panel" / "asistente.py").read_text(encoding="utf-8")
    assert "/root/.hermes" not in codigo


def test_sin_variable_de_entorno_no_hay_clave(asistente, monkeypatch):
    monkeypatch.delenv("MUEBLES_LLM_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert asistente._clave() == ""


def test_limitador_corta_por_ip_y_se_recupera(asistente):
    t = [1000.0]
    lim = asistente.Limitador(por_ip_hora=2, global_dia=100, concurrentes=5, reloj=lambda: t[0])
    for _ in range(2):
        assert lim.pedir("1.1.1.1")[0]
        lim.soltar()
    assert not lim.pedir("1.1.1.1")[0]
    assert lim.pedir("2.2.2.2")[0]  # otra IP no se ve afectada
    lim.soltar()
    t[0] += 3601
    assert lim.pedir("1.1.1.1")[0]


def test_limitador_tope_global_diario(asistente):
    lim = asistente.Limitador(por_ip_hora=99, global_dia=2, concurrentes=5, reloj=lambda: 1.0)
    for ip in ("a", "b"):
        assert lim.pedir(ip)[0]
        lim.soltar()
    assert not lim.pedir("c")[0]


def test_limitador_tope_de_concurrencia(asistente):
    lim = asistente.Limitador(por_ip_hora=99, global_dia=99, concurrentes=1, reloj=lambda: 1.0)
    assert lim.pedir("a")[0]
    assert not lim.pedir("b")[0]  # la plaza sigue ocupada
    lim.soltar()
    assert lim.pedir("b")[0]


# --- Solo modelos gratuitos, con respaldo ---

def test_los_modelos_por_defecto_son_gratuitos(asistente, monkeypatch):
    monkeypatch.delenv("MUEBLES_LLM_MODEL", raising=False)
    lista = asistente.modelos()
    assert lista and all(m.endswith(":free") for m in lista)


def test_un_modelo_de_pago_configurado_se_descarta(asistente, monkeypatch):
    monkeypatch.setenv("MUEBLES_LLM_MODEL", "openai/gpt-4o-mini, a/b:free")
    assert asistente.modelos() == ["a/b:free"]


def test_si_el_primer_modelo_falla_se_prueba_el_siguiente(asistente, monkeypatch):
    import io
    import json

    monkeypatch.setenv("MUEBLES_LLM_MODEL", "uno:free,dos:free")
    monkeypatch.setattr(asistente, "_clave", lambda: "k")
    usados = []

    def falso(peticion, timeout=None):
        modelo = json.loads(peticion.data)["model"]
        usados.append(modelo)
        if modelo == "uno:free":
            raise OSError("saturado")
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())

    monkeypatch.setattr(asistente.urllib.request, "urlopen", falso)
    texto, origen = asistente._redactar("pregunta", [{"fichero": "f", "linea": 1, "texto": "t"}])
    assert (texto, origen) == ("ok", "modelo") and usados == ["uno:free", "dos:free"]
