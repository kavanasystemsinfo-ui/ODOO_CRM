"""Cómo corre la demo en el servidor (hallazgos de la auditoría de noviembre).

  - El temporizador solo restaura si un visitante cambió los datos.
  - El panel, que está expuesto, no corre como root; lo único privilegiado que
    puede hacer es arrancar una unidad de restauración concreta.
"""

from __future__ import annotations

import configparser
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SYSTEMD = Path(__file__).resolve().parents[1] / "scripts" / "systemd"


def _unidad(nombre: str) -> configparser.ConfigParser:
    lector = configparser.ConfigParser(strict=False, interpolation=None)
    lector.optionxform = str
    lector.read(SYSTEMD / nombre, encoding="utf-8")
    return lector


# --- temporizador -----------------------------------------------------------

def test_el_temporizador_ejecuta_la_limpieza_condicional():
    temporizador = _unidad("muebles-restore.timer")
    assert temporizador["Timer"]["Unit"] == "muebles-restore.service"
    orden = _unidad("muebles-restore.service")["Service"]["ExecStart"]
    assert orden.endswith("limpieza_automatica.sh")
    assert "--restaurar" not in orden


BASH = shutil.which("bash")


def _python_falso(carpeta: Path, verificar_sale: int) -> Path:
    """Un «python» que apunta cada orden y responde a --verificar con el código dado."""
    registro = carpeta / "ordenes.txt"
    falso = carpeta / "python_falso"
    falso.write_text(
        "#!/bin/bash\n"
        f'echo "$*" >> "{registro.as_posix()}"\n'
        f'case "$*" in *--verificar*) exit {verificar_sale};; esac\n'
        "exit 0\n",
        encoding="utf-8", newline="\n")
    falso.chmod(falso.stat().st_mode | stat.S_IEXEC)
    return registro


def _limpiar(raiz: Path, tmp_path: Path, verificar_sale: int) -> tuple[int, list[str]]:
    registro = _python_falso(tmp_path, verificar_sale)
    entorno = {**os.environ, "PY": (tmp_path / "python_falso").as_posix(), "LOG": ""}
    proceso = subprocess.run([BASH, (raiz / "panel" / "limpieza_automatica.sh").as_posix()],
                             env=entorno, capture_output=True, text=True, timeout=30)
    ordenes = registro.read_text(encoding="utf-8").splitlines() if registro.exists() else []
    return proceso.returncode, ordenes


@pytest.mark.skipif(BASH is None or sys.platform == "win32", reason="necesita bash de Linux")
def test_laboratorio_intacto_no_se_restaura(raiz, tmp_path):
    codigo, ordenes = _limpiar(raiz, tmp_path, verificar_sale=0)
    assert codigo == 0
    assert len(ordenes) == 1 and "--verificar" in ordenes[0]


@pytest.mark.skipif(BASH is None or sys.platform == "win32", reason="necesita bash de Linux")
def test_laboratorio_tocado_se_restaura(raiz, tmp_path):
    codigo, ordenes = _limpiar(raiz, tmp_path, verificar_sale=1)
    assert codigo == 0
    assert [o.split()[-1] for o in ordenes] == ["--verificar", "--restaurar"]


# --- panel sin root -----------------------------------------------------------

def test_el_panel_no_corre_como_root():
    servicio = _unidad("muebles-panel.service")["Service"]
    assert servicio.get("User") == "muebles-panel"
    assert "/root" not in servicio["ExecStart"]
    assert servicio["BindReadOnlyPaths"].startswith("/root/ODOO_CRM:")
    assert servicio["Environment"]  # MUEBLES_PANEL_CACHE y MUEBLES_RESTORE_UNIT


def test_sudo_solo_permite_arrancar_la_restauracion():
    reglas = [linea for linea in (SYSTEMD / "muebles-panel.sudoers").read_text(
        encoding="utf-8").splitlines() if linea.strip() and not linea.startswith("#")]
    assert reglas == [
        "muebles-panel ALL=(root) NOPASSWD: /usr/bin/systemctl start muebles-restore-ahora.service"
    ]
    assert (SYSTEMD / "muebles-restore-ahora.service").exists()


def test_panel_restaura_por_systemd_si_hay_unidad(panel, monkeypatch):
    monkeypatch.setenv("MUEBLES_RESTORE_UNIT", "muebles-restore-ahora.service")
    assert panel._orden_reinicio() == [
        "/usr/bin/sudo", "-n", "/usr/bin/systemctl", "start", "muebles-restore-ahora.service"]


def test_panel_en_local_lanza_el_script(panel, monkeypatch):
    monkeypatch.delenv("MUEBLES_RESTORE_UNIT", raising=False)
    orden = panel._orden_reinicio()
    assert orden[1].endswith("demo_restaurar_muebles.py")
    assert orden[2:] == ["--restaurar", "--sin-refrescar-panel"]


def test_la_cache_se_puede_sacar_del_checkout(configuracion, monkeypatch, tmp_path):
    monkeypatch.setenv("MUEBLES_PANEL_CACHE", str(tmp_path))
    assert configuracion.carpeta_cache() == tmp_path
    monkeypatch.delenv("MUEBLES_PANEL_CACHE")
    assert configuracion.carpeta_cache().name == "cache_panel"
