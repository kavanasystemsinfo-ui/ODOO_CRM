"""Simulador de la empresa viva: la parte que no necesita Odoo.

Plan de cada tramo (reproducible), horarios, correos ficticios y cómo encaja
con la instantánea y la limpieza automática.
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def plan():
    spec = importlib.util.spec_from_file_location("simulador_plan", RAIZ / "models" / "simulador_plan.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_el_mismo_tramo_da_el_mismo_plan(plan):
    assert plan.plan_tramo("2026-11-10#13") == plan.plan_tramo("2026-11-10#13")
    distintos = {json.dumps(plan.plan_tramo(f"2026-11-{d:02d}#09"), sort_keys=True)
                 for d in range(1, 29)}
    assert len(distintos) > 5, "el plan no varía entre días"


def test_clave_del_tramo(plan):
    martes = datetime(2026, 11, 10, 13, 40)
    assert plan.clave_tramo(martes) == "2026-11-10#13"
    assert plan.clave_tramo(martes.replace(hour=8)) is None
    assert plan.clave_tramo(datetime(2026, 11, 14, 18)) == "2026-11-14#11"  # sábado
    assert plan.clave_tramo(datetime(2026, 11, 15, 12)) is None  # domingo


def test_el_temporizador_lanza_los_mismos_tramos_que_el_plan(plan):
    texto = (RAIZ / "scripts" / "systemd" / "muebles-jornada.timer").read_text(encoding="utf-8")
    calendario = re.findall(r"^OnCalendar=(\S+) \S+ (\S+):05:00 Europe/Madrid$", texto, re.M)
    dias = {"Mon..Fri": range(0, 5), "Sat": (5,)}
    programado = {}
    for nombre, horas in calendario:
        for dia in dias[nombre]:
            programado[dia] = tuple(int(h) for h in horas.split(","))
    esperado = {d: h for d, h in plan.TRAMOS.items() if h}
    assert programado == esperado


@pytest.mark.parametrize("email, ficticio", [
    ("info@hotelmorella.example", True), ("cliente04@example.com", True),
    ("vauxoo@yourcompany.example.com", False), ("compras@reuters.com", False),
    ("john.b@tech.info", False), (None, True), ("", True),
])
def test_solo_valen_dominios_reservados(plan, email, ficticio):
    assert plan.es_email_ficticio(email) is ficticio


def test_los_correos_generados_son_ficticios(plan):
    rng = plan.generador("prueba")
    for _ in range(50):
        empresa = plan.empresa(rng)
        correo = plan.email_ficticio(plan.persona(rng), plan.dominio_ficticio(empresa))
        assert plan.es_email_ficticio(correo), correo
        assert re.fullmatch(r"[a-z.]+@[a-z0-9]+\.example", correo), correo
    assert plan.dominio_ficticio("Moble i Decoració Alzira S.L.") == "mobleidecoracioalzira.example"


def test_el_verificador_usa_los_recuentos_de_la_instantanea(verificador, monkeypatch, tmp_path):
    instantanea = tmp_path / "snap.sql.gz"
    monkeypatch.setenv("MUEBLES_SNAPSHOT", str(instantanea))
    assert verificador.esperado() == verificador.ESPERADO  # sin fichero: publicación
    recuentos = {nombre: valor + 1 for nombre, valor in verificador.ESPERADO.items()}
    verificador.ruta_recuentos().write_text(json.dumps({"recuentos": recuentos}), encoding="utf-8")
    assert verificador.esperado() == recuentos
    verificador.ruta_recuentos().write_text(json.dumps({"recuentos": {"clientes": 1}}),
                                            encoding="utf-8")
    assert verificador.esperado() == verificador.ESPERADO  # fichero incompleto: no se usa


def test_la_jornada_verifica_simula_y_fija_en_ese_orden():
    guion = (RAIZ / "panel" / "jornada.sh").read_text(encoding="utf-8")
    orden = [guion.index(paso) for paso in (
        "flock", "--verificar", "simular_tramo.py", "--fijar-instantanea", "dia_*.json")]
    assert orden == sorted(orden)
    limpieza = (RAIZ / "panel" / "limpieza_automatica.sh").read_text(encoding="utf-8")
    cerrojo = re.search(r'CERROJO="\$\{MUEBLES_CERROJO:-([^}]+)\}"', guion).group(1)
    assert cerrojo in limpieza and limpieza.index("flock") < limpieza.index("--restaurar")


def test_el_simulador_no_se_expone_por_api():
    codigo = (RAIZ / "models" / "simulador_empresa.py").read_text(encoding="utf-8")
    publicos = re.findall(r"^    def ([a-z]\w*)\(", codigo, re.M)
    assert publicos == [], f"métodos públicos (llamables por JSON-2): {publicos}"
    assert "is_superuser()" in codigo
