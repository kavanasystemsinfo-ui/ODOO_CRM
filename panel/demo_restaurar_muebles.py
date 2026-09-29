#!/usr/bin/env python3
"""
Devuelve el laboratorio de muebles (`furniture_db`) a su estado inicial.

Para qué: quien visita la demo entra como administrador y puede tocar todo. Si
deja la aplicación hecha un desastre, este script la devuelve al estado en que
estaba al publicarla, sin depender de nadie.

Cómo: se para Odoo, se rehace la base desde la instantánea canónica y se vuelve a
arrancar. Parar Odoo es imprescindible: con él en marcha quedan conexiones
abiertas y el DROP DATABASE falla o deja la base a medias.

Uso:
    python3 demo_restaurar_muebles.py --estado       # qué instantánea hay y cómo está
    python3 demo_restaurar_muebles.py --dry-run      # imprime los comandos, no ejecuta
    python3 demo_restaurar_muebles.py --restaurar    # restaura (para Odoo ~1 min)
    python3 demo_restaurar_muebles.py --verificar    # compara los recuentos reales
"""

from __future__ import annotations

import argparse
import gzip
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import configuracion  # noqa: E402

BANNER = "Muebles del Hogar S.L. — laboratorio de demostración"

# Recuentos del estado inicial, medidos con SQL antes de publicar.
MANIFIESTO = {
    "productos activos": "SELECT count(*) FROM product_template WHERE active",
    "productos publicados": "SELECT count(*) FROM product_template WHERE is_published",
    "referencias del modelo propio": "SELECT count(*) FROM furniture_product",
    "clientes": "SELECT count(*) FROM res_partner WHERE customer_rank > 0",
    "proveedores": "SELECT count(*) FROM res_partner WHERE supplier_rank > 0",
    "pedidos de venta": "SELECT count(*) FROM sale_order",
    "pedidos confirmados": "SELECT count(*) FROM sale_order WHERE state = 'sale'",
    "presupuestos": "SELECT count(*) FROM sale_order WHERE state IN ('draft','sent')",
    "albaranes": "SELECT count(*) FROM stock_picking",
    "albaranes hechos": "SELECT count(*) FROM stock_picking WHERE state = 'done'",
    "pedidos de compra": "SELECT count(*) FROM purchase_order",
    "asientos contables": "SELECT count(*) FROM account_move",
    "actividades": "SELECT count(*) FROM mail_activity",
    "unidades en almacén": (
        "SELECT round(sum(q.quantity)) FROM stock_quant q "
        "JOIN stock_location l ON l.id = q.location_id "
        "WHERE l.usage = 'internal' AND q.quantity > 0"),
}
ESPERADO = {
    "productos activos": 80,
    "productos publicados": 80,
    "referencias del modelo propio": 80,
    "clientes": 34,
    "proveedores": 5,
    "pedidos de venta": 56,
    "pedidos confirmados": 37,
    "presupuestos": 19,
    "albaranes": 48,
    "albaranes hechos": 41,
    "pedidos de compra": 11,
    "asientos contables": 13,
    "actividades": 31,
    "unidades en almacén": 2190,
}


def _ejecutar(comando: list[str], entrada: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(comando, input=entrada, capture_output=True, check=False)


def _sql(consulta: str) -> int:
    """Un único número, leído del contenedor de PostgreSQL (solo lectura)."""
    res = _ejecutar([configuracion.docker(), "exec", configuracion.contenedor_bd(),
                     "psql", "-U", "odoo", "-d", configuracion.base_de_datos(),
                     "-tAc", consulta])
    if res.returncode != 0:
        raise RuntimeError(res.stderr.decode()[:200])
    return int(float(res.stdout.decode().strip() or 0))


def _psql(sql: str) -> subprocess.CompletedProcess:
    return _ejecutar([configuracion.docker(), "exec", configuracion.contenedor_bd(),
                      "psql", "-v", "ON_ERROR_STOP=1", "-U", "odoo",
                      "-d", "postgres", "-c", sql])


def snapshot_valido() -> tuple[bool, str]:
    """Comprueba que la instantánea existe y que su gzip está íntegro."""
    ruta = configuracion.snapshot()
    if not ruta.exists():
        return False, f"no existe la instantánea {ruta}"
    try:
        with gzip.open(ruta, "rb") as f:
            for _ in range(1, 40):  # leer un poco basta para validar el flujo gzip
                if not f.read(65536):
                    break
    except OSError as exc:
        return False, f"instantánea dañada: {exc}"
    return True, f"{ruta.name} ({ruta.stat().st_size / 1e6:.1f} MB)"


def comandos_restauracion() -> list[str]:
    """Los comandos exactos, para poder enseñarlos antes de ejecutarlos."""
    base = configuracion.base_de_datos()
    return [
        f"{configuracion.docker()} stop {configuracion.contenedor_odoo()}",
        f'{configuracion.docker()} exec {configuracion.contenedor_bd()} psql -U odoo -d postgres '
        f'-c "DROP DATABASE IF EXISTS {base} WITH (FORCE)"',
        f'{configuracion.docker()} exec {configuracion.contenedor_bd()} psql -U odoo -d postgres '
        f'-c "CREATE DATABASE {base} OWNER odoo"',
        f"gunzip -c {configuracion.snapshot()} | {configuracion.docker()} exec -i "
        f"{configuracion.contenedor_bd()} psql -q -U odoo -d {base}",
        f"{configuracion.docker()} start {configuracion.contenedor_odoo()}",
        "esperar a que Odoo responda (hasta 120 s)",
    ]


def odoo_responde(espera: int = 120) -> bool:
    limite = time.time() + espera
    url = f"http://127.0.0.1:{configuracion.puerto_odoo_host()}/web/login"
    while time.time() < limite:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001  (mientras arranca, cualquier fallo es normal)
            pass
        time.sleep(3)
    return False


def restaurar() -> int:
    valido, detalle = snapshot_valido()
    if not valido:
        print(f"NO SE RESTAURA: {detalle}")
        return 1
    print(f"instantánea: {detalle}")

    parar = _ejecutar([configuracion.docker(), "stop", configuracion.contenedor_odoo()])
    if parar.returncode != 0:
        print(f"no se pudo parar Odoo: {parar.stderr.decode()[:200]}")
        return 1
    print("Odoo parado")

    base = configuracion.base_de_datos()
    for sql in (f"DROP DATABASE IF EXISTS {base} WITH (FORCE)",
                f"CREATE DATABASE {base} OWNER odoo"):
        salida = _psql(sql)
        if salida.returncode != 0:
            print(f"fallo en «{sql}»: {salida.stderr.decode()[:300]}")
            return 1
    print("base recreada (vacía)")

    with gzip.open(configuracion.snapshot(), "rb") as f:
        volcado = f.read()
    carga = _ejecutar([configuracion.docker(), "exec", "-i", configuracion.contenedor_bd(),
                       "psql", "-q", "-U", "odoo", "-d", base], entrada=volcado)
    if carga.returncode != 0:
        print(f"fallo al cargar la instantánea: {carga.stderr.decode()[:300]}")
        return 1
    print("instantánea cargada")

    arrancar = _ejecutar([configuracion.docker(), "start", configuracion.contenedor_odoo()])
    if arrancar.returncode != 0:
        print(f"no se pudo arrancar Odoo: {arrancar.stderr.decode()[:200]}")
        return 1
    if not odoo_responde():
        print("Odoo no responde tras 120 s: revisar el log del contenedor")
        return 1
    print("Odoo en marcha")
    return 0


def verificar() -> int:
    """Lee los recuentos reales por SQL y los compara con el manifiesto."""
    fallos = []
    for nombre, consulta in MANIFIESTO.items():
        esperado = ESPERADO[nombre]
        try:
            actual = _sql(consulta)
        except Exception as exc:  # noqa: BLE001
            fallos.append(f"{nombre}: no se puede contar ({exc})")
            print(f"  {nombre:32s} {'?':>7} (esperado {esperado}) NO SE PUEDE LEER")
            continue
        estado = "OK" if actual == esperado else "NO CUADRA"
        print(f"  {nombre:32s} {actual:>7} (esperado {esperado}) {estado}")
        if actual != esperado:
            fallos.append(f"{nombre}: {actual} frente a {esperado}")
    if fallos:
        print("VERIFICACIÓN CON DIFERENCIAS:")
        for f in fallos:
            print("  -", f)
        return 1
    print("VERIFICADO: el laboratorio está en su estado inicial.")
    return 0


def estado() -> int:
    valido, detalle = snapshot_valido()
    print(f"instantánea: {'OK — ' + detalle if valido else 'PROBLEMA — ' + detalle}")
    respondiendo = odoo_responde(espera=3)
    print(f"Odoo responde en 127.0.0.1:{configuracion.puerto_odoo_host()}: "
          f"{'sí' if respondiendo else 'no'}")
    if respondiendo:
        try:
            return verificar()
        except Exception as exc:  # noqa: BLE001
            print(f"no se pudo leer los recuentos: {exc}")
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Devolver el laboratorio de muebles a su estado inicial")
    parser.add_argument("--estado", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restaurar", action="store_true")
    parser.add_argument("--verificar", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        for i, comando in enumerate(comandos_restauracion(), 1):
            print(f"{i}. {comando}")
        return 0
    if args.restaurar:
        return restaurar()
    if args.verificar:
        return verificar()
    if args.estado:
        return estado()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
