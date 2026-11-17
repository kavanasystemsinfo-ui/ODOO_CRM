"""La instantánea canónica y el nombre del perfil de Hermes.

Qué pasó: el perfil de Hermes que guarda la instantánea se llamaba "hermes2" y pasó a llamarse
"kavana". La simulación diaria y la limpieza automática buscaban la ruta vieja, no la
encontraban y fallaron durante días sin que nada avisara. Estas pruebas fijan que:
  * la variable MUEBLES_SNAPSHOT manda,
  * se usa la primera carpeta que existe (la nueva antes que la antigua),
  * y ningún otro fichero del repo vuelve a dar por fijo el nombre del perfil.
"""

from __future__ import annotations

from pathlib import Path

NOMBRE = "snapshot_muebles_demo_canonico.sql.gz"


def _preparar(configuracion, monkeypatch, tmp_path, existentes: list[str]) -> list[str]:
    """Crea carpetas falsas (algunas con la instantánea) y las pone como candidatas."""
    carpetas = []
    for nombre in ("nueva", "antigua"):
        carpeta = tmp_path / nombre
        carpeta.mkdir()
        if nombre in existentes:
            (carpeta / NOMBRE).write_bytes(b"x")
        carpetas.append(str(carpeta) + "/")
    monkeypatch.setattr(configuracion, "CARPETAS_SNAPSHOT", tuple(carpetas))
    monkeypatch.delenv("MUEBLES_SNAPSHOT", raising=False)
    return carpetas


def test_la_variable_de_entorno_manda(configuracion, monkeypatch, tmp_path):
    _preparar(configuracion, monkeypatch, tmp_path, ["nueva"])
    monkeypatch.setenv("MUEBLES_SNAPSHOT", "/otro/sitio/instantanea.sql.gz")
    assert configuracion.snapshot() == Path("/otro/sitio/instantanea.sql.gz")


def test_usa_la_carpeta_nueva_aunque_exista_la_antigua(configuracion, monkeypatch, tmp_path):
    carpetas = _preparar(configuracion, monkeypatch, tmp_path, ["nueva", "antigua"])
    assert configuracion.snapshot() == Path(carpetas[0]) / NOMBRE


def test_si_solo_existe_la_antigua_la_encuentra(configuracion, monkeypatch, tmp_path):
    carpetas = _preparar(configuracion, monkeypatch, tmp_path, ["antigua"])
    assert configuracion.snapshot() == Path(carpetas[1]) / NOMBRE


def test_si_no_existe_ninguna_devuelve_la_ruta_actual(configuracion, monkeypatch, tmp_path):
    """Para que el error enseñe la ruta que hay que arreglar, no la del nombre antiguo."""
    _preparar(configuracion, monkeypatch, tmp_path, [])
    assert configuracion.snapshot() == Path(configuracion.SNAPSHOT_POR_DEFECTO)
    assert "hermes2" not in configuracion.SNAPSHOT_POR_DEFECTO


def test_ningun_otro_fichero_da_por_fijo_el_nombre_del_perfil(raiz):
    """Solo configuracion.py puede nombrar el perfil antiguo (como respaldo y comentado)."""
    ofensores = []
    for carpeta in ("panel", "scripts", "ci", "config", "demo.sh"):
        ruta = raiz / carpeta
        ficheros = [ruta] if ruta.is_file() else [
            f for f in ruta.rglob("*") if f.is_file() and f.suffix in {".py", ".sh", ".yml", ".yaml", ".conf", ".service"}
        ]
        for fichero in ficheros:
            if fichero.name == "configuracion.py":
                continue
            if "hermes2" in fichero.read_text(encoding="utf-8", errors="ignore"):
                ofensores.append(str(fichero.relative_to(raiz)))
    assert not ofensores, f"estos ficheros dan por fijo el perfil antiguo 'hermes2': {ofensores}"
