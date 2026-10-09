#!/usr/bin/env python3
"""Lint OCA del módulo (oca-checks-odoo-module, el linter oficial de la OCA).

Por qué existe: el repo usa layout "repo = módulo" y el linter OCA busca el
manifiesto subiendo desde cada fichero hasta la raíz git *sin revisarla*, así
que in situ no encuentra nunca el módulo (walk_up de oca_pre_commit_hooks se
detiene en top_path, que con .git en la raíz es la propia raíz). Su diseño
asume repos multi-módulo tipo OCA/web donde cada subdirectorio es un módulo.

Cómo lo resuelve: copia las carpetas del módulo a un directorio temporal sin
.git y lintea allí, donde el walk_up sí sube hasta el manifiesto. Solo stdlib.

Uso:
    pip install oca-odoo-pre-commit-hooks
    python scripts/lint_oca.py            # 0 si limpio, 1 si hay hallazgos
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETAS = ("models", "views", "controllers", "security", "data")
FICHEROS = ("__init__.py", "__manifest__.py")


def main() -> int:
    try:
        from oca_pre_commit_hooks.checks_odoo_module import run
    except ImportError:
        print("Falta la dependencia: pip install oca-odoo-pre-commit-hooks")
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / "modulo"
        destino.mkdir()
        for carpeta in CARPETAS:
            shutil.copytree(RAIZ / carpeta, destino / carpeta)
        for fichero in FICHEROS:
            shutil.copy2(RAIZ / fichero, destino / fichero)

        # El linter trabaja sobre la lista de ficheros "cambiados": se le
        # pasan todos los del módulo copiado.
        objetivos = [str(p) for p in destino.rglob("*") if p.is_file()]
        os.chdir(destino)
        hallazgos = run(files_or_modules=objetivos, no_exit=True, no_verbose=True)

    if hallazgos:
        for h in hallazgos:
            print(h)
        print(f"\n{len(hallazgos)} hallazgo(s) del linter OCA")
        return 1
    print("Lint OCA: 0 hallazgos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
