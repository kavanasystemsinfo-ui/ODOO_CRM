"""Copias de prueba por visitante: firma de la cookie, nombres, limpieza y configuración."""

from __future__ import annotations

import configparser
import importlib.util
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SECRETO = "secreto-de-prueba"


@pytest.fixture(scope="module")
def firma():
    spec = importlib.util.spec_from_file_location("pruebas_firma", RAIZ / "models" / "pruebas_firma.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_nombres_solo_los_nuestros(firma):
    nombre = firma.nuevo_nombre()
    assert firma.nombre_valido(nombre)
    assert nombre != firma.nuevo_nombre()
    for malo in ("furniture_db", "muebles_plantilla", 'muebles_demo_x"; DROP', "muebles_demo_AB12",
                 "muebles_demo_abc", None, ""):
        assert not firma.nombre_valido(malo), malo


def test_la_cookie_firmada_se_verifica_y_caduca(firma):
    valor = firma.firmar("muebles_demo_abcd1234", 2000, SECRETO)
    assert firma.verificar(valor, SECRETO, ahora=1999) == ("muebles_demo_abcd1234", 2000)
    assert firma.verificar(valor, SECRETO, ahora=2000) is None          # caducada
    assert firma.verificar(valor, "otro-secreto", ahora=1999) is None   # otra clave
    assert firma.verificar(valor, "", ahora=1999) is None               # sin clave


def test_no_se_puede_apuntar_a_la_copia_de_otro(firma):
    valor = firma.firmar("muebles_demo_abcd1234", 2000, SECRETO)
    ajena = valor.replace("abcd1234", "zzzz9999")
    alargada = valor.replace(".2000.", ".9999.")
    for trucada in (ajena, alargada, "muebles_demo_abcd1234.2000.", "basura"):
        assert firma.verificar(trucada, SECRETO, ahora=1) is None, trucada
    with pytest.raises(ValueError):
        firma.firmar("furniture_db", 2000, SECRETO)
    with pytest.raises(ValueError):
        firma.firmar("muebles_demo_abcd1234", 2000, "")


def test_caducidad_guardada_en_la_base(firma):
    assert firma.leer_caducidad(firma.comentario(1234)) == 1234
    assert firma.leer_caducidad(None) == 0          # sin comentario: caducada
    assert firma.leer_caducidad("lo que sea") == 0


def test_que_se_borra_y_cuando_hay_plaza(firma):
    ahora = 10_000
    copias = {"muebles_demo_aaaa1111": ahora - firma.GRACIA - 1,   # caducó hace rato
              "muebles_demo_bbbb2222": ahora - 10,                 # caducó, aún en gracia
              "muebles_demo_cccc3333": ahora + 1800,
              "muebles_demo_dddd4444": 0}                          # sin comentario
    assert firma.a_borrar(copias, ahora) == ["muebles_demo_aaaa1111", "muebles_demo_dddd4444"]
    assert firma.plazas_ocupadas(copias, ahora) == 4
    assert firma.libre_en_minutos({"muebles_demo_cccc3333": ahora + 600}, ahora) == 16


@pytest.mark.parametrize("borradas, vivas, viejas_antes, esperado", [
    (0, 2, 0, (False, 0)),   # nada que soltar
    (1, 0, 0, (True, 0)),    # nadie probando: se reinicia sin molestar
    (1, 2, 0, (False, 1)),   # hay gente: se espera
    (1, 1, 2, (True, 0)),    # demasiadas bases muertas en memoria
])
def test_cuando_reiniciar_el_odoo_de_pruebas(firma, borradas, vivas, viejas_antes, esperado):
    assert firma.reiniciar_odoo(borradas, vivas, viejas_antes) == esperado


def test_el_odoo_de_pruebas_solo_ve_copias(firma):
    conf = configparser.ConfigParser()
    conf.read(RAIZ / "config" / "odoo_pruebas.conf", encoding="utf-8")
    opciones = conf["options"]
    filtro = re.compile(opciones["dbfilter"])
    assert filtro.fullmatch(firma.nuevo_nombre())
    for otra in ("furniture_db", "muebles_plantilla", "muebles_plantilla_nueva", "postgres"):
        assert not filtro.fullmatch(otra), otra
    assert opciones["list_db"] == "False"
    assert opciones["max_cron_threads"] == "0"
    assert "ODOO_CRM" in opciones["server_wide_modules"].split(",")


def test_la_demo_no_expone_el_gestor_de_bases():
    conf = configparser.ConfigParser()
    conf.read(RAIZ / "config" / "odoo.conf", encoding="utf-8")
    assert conf["options"]["list_db"] == "False"


def test_caddy_manda_la_cookie_al_odoo_de_pruebas(firma):
    bloque = (RAIZ / "scripts" / "caddy" / "odoocrm.caddy").read_text(encoding="utf-8")
    assert firma.COOKIE in bloque and "localhost:8072" in bloque
    assert bloque.index("@prueba") < bloque.index("reverse_proxy localhost:8070")
    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert "127.0.0.1:8072:8069" in compose and "odoo_pruebas.conf" in compose


def test_la_jornada_renueva_la_plantilla_despues_de_fijar():
    guion = (RAIZ / "panel" / "jornada.sh").read_text(encoding="utf-8")
    assert guion.index("--fijar-instantanea") < guion.index("plantilla_pruebas.sh")
