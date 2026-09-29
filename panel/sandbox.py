#!/usr/bin/env python3
"""Portero del laboratorio por visitante.

Cada visitante recibe su propia base de datos, clonada de una plantilla, para
que pueda romper lo que quiera sin pisar a nadie, y para que el botón de
reiniciar solo afecte a la suya.

Reparto de responsabilidades:
  - La lógica pura (nombre de la base, cookie firmada, caducidad y a quién
    reciclar) vive aquí y se prueba sin tocar ninguna base.
  - Las operaciones contra Postgres van por `docker exec psql`, igual que el
    panel, sin dependencias.

La plantilla NO se sirve nunca: Odoo del laboratorio de visitantes filtra por
`^muebles_demo_[a-z0-9]{4,12}$`, así que `muebles_plantilla` queda fuera.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import subprocess
import time
from hashlib import sha256
from pathlib import Path

CARPETA = Path(__file__).resolve().parent

PREFIJO = "muebles_demo_"
PLANTILLA = os.environ.get("MUEBLES_PLANTILLA", "muebles_plantilla")
BASE_DATOS_PG = "postgres"
REGISTRO = Path(os.environ.get("MUEBLES_REGISTRO", str(CARPETA / "sandbox_registro.json")))
COOKIE = "muebles_lab"
TOPE_POR_DEFECTO = 3
TTL_POR_DEFECTO = 4 * 3600  # cuatro horas

# El secreto firma la cookie: sin él, cualquiera podría ponerse el nombre de la
# base de otro visitante y entrar en su laboratorio.
SECRETO_POR_DEFECTO = ""


def tope() -> int:
    return int(os.environ.get("MUEBLES_TOPE", TOPE_POR_DEFECTO) or TOPE_POR_DEFECTO)


def ttl() -> int:
    return int(os.environ.get("MUEBLES_TTL", TTL_POR_DEFECTO) or TTL_POR_DEFECTO)


def secreto() -> str:
    return os.environ.get("MUEBLES_SECRETO", "").strip() or SECRETO_POR_DEFECTO


def nombre_valido(nombre: str) -> bool:
    """Solo lo que generamos nosotros: evita inyecciones en el SQL del portero."""
    if not nombre.startswith(PREFIJO):
        return False
    cola = nombre[len(PREFIJO):]
    return 4 <= len(cola) <= 12 and all(c in "abcdefghijklmnopqrstuvwxyz0123456789" for c in cola)


def nuevo_nombre() -> str:
    return PREFIJO + secrets.token_hex(4)  # 8 caracteres hexadecimales


def firmar(nombre: str, clave: str | None = None) -> str:
    clave = clave if clave is not None else secreto()
    mac = hmac.new(clave.encode("utf-8"), nombre.encode("utf-8"), sha256).hexdigest()
    return f"{nombre}.{mac}"


def verificar(cookie: str, clave: str | None = None) -> str | None:
    """Devuelve el nombre de la base si la cookie es válida, o None."""
    clave = clave if clave is not None else secreto()
    if not cookie or "." not in cookie or not clave:
        return None
    nombre, _, mac = cookie.rpartition(".")
    if not nombre_valido(nombre):
        return None
    esperado = hmac.new(clave.encode("utf-8"), nombre.encode("utf-8"), sha256).hexdigest()
    return nombre if hmac.compare_digest(mac, esperado) else None


# ---------------------------------------------------------------------------
# Registro de visitantes (quién tiene qué laboratorio y desde cuándo)
# ---------------------------------------------------------------------------

def leer_registro() -> dict:
    try:
        return json.loads(REGISTRO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def escribir_registro(datos: dict) -> None:
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def caducados(registro: dict, ahora: float | None = None, vida: int | None = None) -> list[str]:
    """Bases de visitantes que ya han pasado su vida útil."""
    ahora = time.time() if ahora is None else ahora
    vida = ttl() if vida is None else vida
    return [nombre for nombre, datos in registro.items()
            if ahora - float(datos.get("visto", 0)) > vida]


def a_reciclar(registro: dict, limite: int | None = None) -> str | None:
    """Si hay más visitantes que plazas, la base más antigua es la que cae."""
    limite = tope() if limite is None else limite
    if len(registro) < limite:
        return None
    return min(registro, key=lambda nombre: float(registro[nombre].get("visto", 0)))


# ---------------------------------------------------------------------------
# Postgres (crear, borrar y listar bases de visitantes)
# ---------------------------------------------------------------------------

def _psql(consulta: str, base: str = BASE_DATOS_PG) -> str:
    import configuracion

    resultado = subprocess.run(
        [configuracion.docker(), "exec", configuracion.contenedor_bd(),
         "psql", "-U", "odoo", "-d", base, "-tAc", consulta],
        capture_output=True, text=True, timeout=120,
    )
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.strip()[:200])
    return resultado.stdout.strip()


def existe(nombre: str) -> bool:
    return bool(_psql(f"select 1 from pg_database where datname = '{nombre}'"))


def crear(nombre: str) -> None:
    """Clon instantáneo de la plantilla. La plantilla no puede tener conexiones."""
    if not nombre_valido(nombre):
        raise ValueError(f"nombre de base no válido: {nombre}")
    _psql(f'create database "{nombre}" template "{PLANTILLA}"')


def borrar(nombre: str) -> None:
    if not nombre_valido(nombre):
        raise ValueError(f"nombre de base no válido: {nombre}")
    _psql(f'select pg_terminate_backend(pid) from pg_stat_activity where datname = \'{nombre}\'')
    _psql(f'drop database if exists "{nombre}"')


def tamanos() -> list[tuple[str, str]]:
    salida = _psql("select datname, pg_size_pretty(pg_database_size(datname)) "
                   f"from pg_database where datname like '{PREFIJO}%' order by datname")
    filas: list[tuple[str, str]] = []
    for linea in salida.splitlines():
        if not linea.strip():
            continue
        nombre, _, tamano = linea.partition("|")
        filas.append((nombre, tamano))
    return filas


def reiniciar(nombre: str) -> None:
    """Deja el laboratorio del visitante como recién creado."""
    borrar(nombre)
    crear(nombre)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "listar":
        print(json.dumps(tamanos(), ensure_ascii=False, indent=2))
    elif len(sys.argv) > 2 and sys.argv[1] == "crear":
        crear(sys.argv[2])
        print(f"creada {sys.argv[2]}")
    elif len(sys.argv) > 2 and sys.argv[1] == "borrar":
        borrar(sys.argv[2])
        print(f"borrada {sys.argv[2]}")
    else:
        print("uso: sandbox.py listar | crear <nombre> | borrar <nombre>")
