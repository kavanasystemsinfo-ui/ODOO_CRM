"""Comprobaciones contra el laboratorio en marcha (Odoo, PostgreSQL y panel).

Se saltan solas salvo que se pidan con `MUEBLES_LAB=1`, porque necesitan los
contenedores del laboratorio y la red local. En CI no se ejecutan.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

pytestmark = [
    pytest.mark.vivo,
    pytest.mark.skipif(os.environ.get("MUEBLES_LAB") != "1",
                       reason="necesita el laboratorio en marcha (MUEBLES_LAB=1)"),
]


def _json(url: str, tiempo: int = 15) -> dict:
    with urllib.request.urlopen(url, timeout=tiempo) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def test_el_verificador_del_laboratorio_pasa(configuracion):
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / "panel" / "demo_restaurar_muebles.py"), "--verificar"],
        capture_output=True, text=True, timeout=180,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "VERIFICADO" in resultado.stdout


def test_el_panel_del_dia_responde(configuracion):
    datos = _json(f"http://127.0.0.1:{configuracion.puerto_panel()}/api/dia")
    for clave in ("productos", "unidades", "salud_dato"):
        assert clave in datos, f"el panel no devuelve {clave}"


def test_odoo_responde_en_su_puerto(configuracion):
    url = f"http://127.0.0.1:{configuracion.puerto_odoo_host()}/web/login"
    with urllib.request.urlopen(url, timeout=15) as respuesta:
        assert respuesta.status == 200
