"""El portero del laboratorio por visitante: lo que se prueba sin base de datos.

Aquí va lo que sostiene la seguridad y el orden: que solo se acepten nombres de
base generados por nosotros, que la cookie no se pueda falsificar, cuándo caduca
un laboratorio y a quién se recicla cuando se llena el aforo.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

CONF_SANDBOX = Path("/root/.hermes/profiles/hermes2/odoo_sandbox.conf")


def test_nombre_valido_acepta_lo_que_generamos(sandbox):
    assert sandbox.nombre_valido("muebles_demo_a1b2c3d4")
    assert sandbox.nombre_valido("muebles_demo_abcdef")


@pytest.mark.parametrize("nombre", [
    "furniture_db",
    "muebles_plantilla",
    "muebles_demo_",
    "muebles_demo_ab",              # demasiado corto
    "muebles_demo_abcdefghijklm",   # demasiado largo
    "muebles_demo_AB12",            # mayúsculas fuera
    "muebles_demo_x'; drop database furniture_db; --",
    "muebles_demo_ábcdef",
])
def test_nombre_valido_rechaza_lo_demas(sandbox, nombre):
    assert not sandbox.nombre_valido(nombre)


def test_nuevo_nombre_es_valido_y_distinto(sandbox):
    nombres = {sandbox.nuevo_nombre() for _ in range(20)}
    assert len(nombres) == 20
    assert all(sandbox.nombre_valido(n) for n in nombres)


def test_cookie_firmada_ida_y_vuelta(sandbox):
    cookie = sandbox.firmar("muebles_demo_a1b2c3d4", "clave-de-prueba")
    assert sandbox.verificar(cookie, "clave-de-prueba") == "muebles_demo_a1b2c3d4"


@pytest.mark.parametrize("cookie", [
    "",
    "sin-punto",
    "muebles_demo_a1b2c3d4",
    "furniture_db.firmafalsa",
    "muebles_demo_a1b2c3d4.firmafalsa",
])
def test_cookie_manipulada_no_cuela(sandbox, cookie):
    assert sandbox.verificar(cookie, "clave-de-prueba") is None


def test_cookie_de_otro_secreto_no_cuela(sandbox):
    cookie = sandbox.firmar("muebles_demo_a1b2c3d4", "clave-de-prueba")
    assert sandbox.verificar(cookie, "otra-clave") is None


def test_sin_secreto_configurado_no_se_fia_de_nada(sandbox, monkeypatch):
    monkeypatch.delenv("MUEBLES_SECRETO", raising=False)
    monkeypatch.setattr(sandbox, "SECRETO_POR_DEFECTO", "")
    cookie = sandbox.firmar("muebles_demo_a1b2c3d4", "clave")
    assert sandbox.verificar(cookie) is None


def test_caducan_los_laboratorios_viejos(sandbox):
    ahora = 1_000_000.0
    registro = {
        "muebles_demo_vieja": {"visto": ahora - 5 * 3600},
        "muebles_demo_media": {"visto": ahora - 3600},
        "muebles_demo_nueva": {"visto": ahora - 60},
    }
    assert sandbox.caducados(registro, ahora=ahora, vida=4 * 3600) == ["muebles_demo_vieja"]


def test_no_se_recicla_nadie_si_sobra_sitio(sandbox):
    registro = {"muebles_demo_uno": {"visto": 100.0}, "muebles_demo_dos": {"visto": 200.0}}
    assert sandbox.a_reciclar(registro, limite=3) is None


def test_al_llenarse_cae_el_mas_antiguo(sandbox):
    registro = {
        "muebles_demo_uno": {"visto": 300.0},
        "muebles_demo_dos": {"visto": 100.0},
        "muebles_demo_tres": {"visto": 200.0},
    }
    assert sandbox.a_reciclar(registro, limite=3) == "muebles_demo_dos"


def test_crear_y_borrar_rechazan_nombres_ajenos(sandbox):
    for nombre in ("furniture_db", "muebles_plantilla", "otra_cosa"):
        with pytest.raises(ValueError):
            sandbox.crear(nombre)
        with pytest.raises(ValueError):
            sandbox.borrar(nombre)


def test_el_tope_y_la_vida_se_pueden_configurar(sandbox, monkeypatch):
    monkeypatch.setenv("MUEBLES_TOPE", "5")
    monkeypatch.setenv("MUEBLES_TTL", "600")
    assert sandbox.tope() == 5
    assert sandbox.ttl() == 600


@pytest.mark.skipif(not CONF_SANDBOX.exists(), reason="config del Odoo de visitantes fuera del repositorio")
def test_el_odoo_de_visitantes_sirve_solo_sus_bases(sandbox):
    """La plantilla no puede servirse nunca, y el filtro debe aceptar los clones."""
    import re

    linea = [l for l in CONF_SANDBOX.read_text(encoding="utf-8").splitlines() if l.startswith("dbfilter")]
    assert linea, "la configuración no declara dbfilter"
    patron = linea[0].split("=", 1)[1].strip()
    assert re.search(patron, "muebles_demo_a1b2c3d4"), patron
    assert not re.search(patron, sandbox.PLANTILLA), patron
    assert not re.search(patron, "furniture_db"), patron
