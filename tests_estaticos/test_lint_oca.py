"""El linter OCA contra el módulo.

Corre scripts/lint_oca.py de verdad (subprocess). Si la dependencia
oca-odoo-pre-commit-hooks no está instalada, se salta: la suite básica
sigue siendo solo pytest.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(
    importlib.util.find_spec("oca_pre_commit_hooks") is None,
    reason="oca-odoo-pre-commit-hooks no está instalado",
)
def test_el_modulo_pasa_el_linter_oca():
    resultado = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "lint_oca.py")],
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, f"{resultado.stdout}\n{resultado.stderr}"
    assert "0 hallazgos" in resultado.stdout
