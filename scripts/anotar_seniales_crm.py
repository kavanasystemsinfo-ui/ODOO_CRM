#!/usr/bin/env python3
"""Anota las señales comerciales de las oportunidades del CRM del laboratorio.

Por qué: el módulo puntúa con cinco señales, pero tres de ellas (`x_es_contrato`,
`x_proyecto_referenciado`, `x_muestra_pedida`) las marca el comercial y en la
demo nadie las había marcado. Sin ellas el score de TODAS las oportunidades
era 10 (solo el email corporativo) y la sugerencia de la capa MCP siempre era
la de nurturing: la mecánica funcionaba pero no se veía.

Qué hace: marca señales que el propio título de la oportunidad ya dice de
forma explícita. No inventa información: si el título dice "Contrato de
distribución", la oportunidad ES un contract; si dice "Solicita catálogo 2026",
la muestra está pedida. La regla está escrita aquí, es reproducible y se
puede revertir poniendo las tres columnas a NULL.

Uso:
    python3 scripts/anotar_seniales_crm.py            # muestra qué anotaría
    python3 scripts/anotar_seniales_crm.py --aplicar  # lo escribe en la base
"""

from __future__ import annotations

import argparse
import subprocess
import sys

BASE = "furniture_db"
CONTENEDOR = "furniture_db"

# Regla: si el título dice esto, la señal está marcada.
REGLAS = {
    "x_es_contrato": ("contract", "distribu"),
    "x_proyecto_referenciado": (
        "proyecto", "presupuesto", "renovaci", "sustituci", "equipamiento",
        "reforma", "diseño", "modernizar", "valoraci",
    ),
    "x_muestra_pedida": ("catálogo",),
}


def consultar(consulta: str) -> str:
    salida = subprocess.run(
        ["docker", "exec", CONTENEDOR, "psql", "-U", "odoo", "-d", BASE,
         "-tAc", consulta],
        capture_output=True, text=True, check=True,
    )
    return salida.stdout.strip()


def oportunidades() -> list[tuple[int, str]]:
    lineas = consultar("select id || '|' || name from crm_lead order by id")
    resultado = []
    for linea in lineas.splitlines():
        if not linea.strip():
            continue
        identificador, _, nombre = linea.partition("|")
        resultado.append((int(identificador), nombre))
    return resultado


def senales_de(titulo: str) -> dict[str, bool]:
    minusculas = titulo.lower()
    return {columna: any(palabra in minusculas for palabra in palabras)
            for columna, palabras in REGLAS.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true",
                        help="escribe las señales en la base (por defecto solo muestra)")
    args = parser.parse_args()

    plan = []
    for identificador, titulo in oportunidades():
        senales = senales_de(titulo)
        if any(senales.values()):
            plan.append((identificador, titulo, senales))

    for identificador, titulo, senales in plan:
        marcas = ", ".join(f"{columna.replace('x_', '')}={'sí' if valor else 'no'}"
                           for columna, valor in senales.items())
        print(f"{identificador:>3} | {titulo[:58]:58} | {marcas}")

    if not args.aplicar:
        print(f"\n{len(plan)} oportunidades con señales deducibles del título "
              "(no se ha escrito nada: usa --aplicar)")
        return 0

    for identificador, titulo, senales in plan:
        valores = ", ".join(f"{columna}={'true' if valor else 'false'}"
                            for columna, valor in senales.items())
        consultar(f"update crm_lead set {valores} where id = {identificador}")
        print(f"anotada: {identificador}")

    print("\n=== como queda el score ===")
    sys.path.insert(0, "/root/ODOO_CRM/models")
    import importlib.util

    ruta = "/root/ODOO_CRM/models/lead_scoring.py"
    spec = importlib.util.spec_from_file_location("lead_scoring", ruta)
    scoring = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scoring)

    for identificador, titulo in oportunidades()[:12]:
        fila = consultar(
            "select coalesce(x_es_contrato,false) || '|' || "
            "coalesce(x_proyecto_referenciado,false) || '|' || "
            "coalesce(x_muestra_pedida,false) from crm_lead where id = "
            f"{identificador}")
        partes = fila.split("|")
        senales = {
            "tipo_contrato": partes[0] == "true",
            "proyecto_referenciado": partes[1] == "true",
            "muestra_pedida": partes[2] == "true",
        }
        score = scoring.puntuar(senales)
        print(f"{identificador:>3} | score {score:>3} | {scoring.prioridad_sugerida(score):7} | {titulo[:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
