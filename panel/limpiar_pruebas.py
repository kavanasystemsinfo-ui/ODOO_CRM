#!/usr/bin/env python3
"""Borra las copias de prueba caducadas y suelta su memoria.

Lo lanza muebles-pruebas-limpieza.timer cada 5 minutos, como root:

  1. Lee las copias (bases «muebles_demo_*») y cuándo caduca cada una, que va
     escrito en la propia base (COMMENT ON DATABASE).
  2. Borra las que caducaron hace más de la gracia, con sus ficheros, y los
     ficheros huérfanos de copias que ya no existen.
  3. Reinicia el Odoo de pruebas si así se suelta memoria sin molestar: Odoo
     guarda en memoria cada base que ha servido y no la libera al borrarla.

Comparte el cerrojo del laboratorio para no reiniciar Odoo mientras se
prepara la plantilla.
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCKER = os.environ.get("MUEBLES_DOCKER", "/usr/bin/docker")
BD = os.environ.get("MUEBLES_DB_CONTAINER", "furniture_db")
ODOO_PRUEBAS = os.environ.get("MUEBLES_ODOO_PRUEBAS", "furniture_odoo_pruebas")
FILESTORE = Path(os.environ.get("MUEBLES_FILESTORE",
                                "/var/lib/docker/volumes/odoo_crm_odoo_data/_data/filestore"))
ESTADO = Path(os.environ.get("MUEBLES_PRUEBAS_ESTADO", "/var/lib/muebles/pruebas.json"))
CERROJO = os.environ.get("MUEBLES_CERROJO", "/run/muebles-laboratorio.lock")


def _firma():
    spec = importlib.util.spec_from_file_location("pruebas_firma", REPO / "models" / "pruebas_firma.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


firma = _firma()


def _psql(sql: str) -> str:
    salida = subprocess.run(
        [DOCKER, "exec", BD, "psql", "-v", "ON_ERROR_STOP=1", "-U", "odoo", "-d", "postgres",
         "-tAc", sql], capture_output=True, text=True, check=False)
    if salida.returncode != 0:
        raise RuntimeError(salida.stderr.strip()[:300])
    return salida.stdout


def copias() -> dict[str, int]:
    filas = _psql("SELECT datname || '|' || coalesce(shobj_description(oid, 'pg_database'), '') "
                  f"FROM pg_database WHERE datname LIKE '{firma.PREFIJO}%'")
    resultado = {}
    for linea in filas.splitlines():
        nombre, _, texto = linea.partition("|")
        if firma.nombre_valido(nombre):
            resultado[nombre] = firma.leer_caducidad(texto)
    return resultado


def _leer_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_estado(datos: dict) -> None:
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(datos), encoding="utf-8")


def main() -> int:
    with open(CERROJO, "w") as cerrojo:
        try:
            fcntl.flock(cerrojo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("laboratorio ocupado (jornada o plantilla): se deja para la próxima")
            return 0
        ahora = time.time()
        existentes = copias()
        borrar = firma.a_borrar(existentes, ahora)
        for nombre in borrar:
            _psql(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')
            shutil.rmtree(FILESTORE / nombre, ignore_errors=True)
            print(f"copia borrada: {nombre}")
        vivas = {n: c for n, c in existentes.items() if n not in borrar}
        if FILESTORE.is_dir():
            for carpeta in FILESTORE.glob(firma.PREFIJO + "*"):
                if firma.nombre_valido(carpeta.name) and carpeta.name not in existentes:
                    shutil.rmtree(carpeta, ignore_errors=True)
                    print(f"ficheros huérfanos borrados: {carpeta.name}")
        estado = _leer_estado()
        reiniciar, viejas = firma.reiniciar_odoo(len(borrar), len(vivas), int(estado.get("viejas", 0)))
        if reiniciar:
            subprocess.run([DOCKER, "restart", ODOO_PRUEBAS], check=False, capture_output=True)
            print(f"Odoo de pruebas reiniciado (quedan {len(vivas)} copias en uso)")
        _guardar_estado({"viejas": viejas, "revisado": int(ahora), "vivas": sorted(vivas)})
        if borrar or reiniciar:
            print(f"{len(vivas)} copias en uso, {viejas} bases borradas aún en memoria")
    return 0


if __name__ == "__main__":
    sys.exit(main())
