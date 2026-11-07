"""Configuración del laboratorio de muebles, en un solo sitio.

Por qué existe: el panel del día y el motor de restauración tienen que hablar de
la misma base, del mismo contenedor y de la misma instantánea. Aquí vive la
única respuesta a esas preguntas; si algún día se apunta a otra instancia, se
cambia por variable de entorno y no hay que tocar código.
"""

from __future__ import annotations

import os
from pathlib import Path

CARPETA = Path(__file__).resolve().parent

# Rutas por defecto (laboratorio de este servidor).
DOCKER_POR_DEFECTO = "/usr/bin/docker"
BASE_POR_DEFECTO = "furniture_db"
CONTENEDOR_BD_POR_DEFECTO = "furniture_db"
CONTENEDOR_ODOO_POR_DEFECTO = "furniture_odoo"
PUERTO_ODOO_HOST_POR_DEFECTO = 8070  # 8070 en el host -> 8069 dentro del contenedor
PUERTO_PANEL_POR_DEFECTO = 8081
ESPERA_MINIMA_REINICIO_POR_DEFECTO = 180  # segundos entre reinicios
SNAPSHOT_POR_DEFECTO = (
    "/root/.hermes/profiles/hermes2/trabajo/muebles-demo/"
    "snapshot_muebles_demo_canonico.sql.gz"
)

# API externa de Odoo (JSON-2). La API key del usuario de integración NO tiene
# valor por defecto: sin MUEBLES_ODOO_API_KEY el panel no arranca la lectura.
PANEL_HOST_POR_DEFECTO = "127.0.0.1"  # solo loopback; el proxy publica /panel


def _texto(clave: str, por_defecto: str) -> str:
    return os.environ.get(clave, "").strip() or por_defecto


def docker() -> str:
    return _texto("MUEBLES_DOCKER", DOCKER_POR_DEFECTO)


def base_de_datos() -> str:
    return _texto("MUEBLES_DB", BASE_POR_DEFECTO)


def contenedor_bd() -> str:
    return _texto("MUEBLES_DB_CONTAINER", CONTENEDOR_BD_POR_DEFECTO)


def contenedor_odoo() -> str:
    return _texto("MUEBLES_ODOO_CONTAINER", CONTENEDOR_ODOO_POR_DEFECTO)


def puerto_odoo_host() -> int:
    return int(_texto("MUEBLES_ODOO_PORT", str(PUERTO_ODOO_HOST_POR_DEFECTO)))


def puerto_panel() -> int:
    return int(_texto("MUEBLES_PANEL_PORT", str(PUERTO_PANEL_POR_DEFECTO)))


def espera_minima_reinicio() -> int:
    return int(_texto("MUEBLES_ESPERA_REINICIO", str(ESPERA_MINIMA_REINICIO_POR_DEFECTO)))


def snapshot() -> Path:
    return Path(_texto("MUEBLES_SNAPSHOT", SNAPSHOT_POR_DEFECTO))


def panel_host() -> str:
    return _texto("MUEBLES_PANEL_HOST", PANEL_HOST_POR_DEFECTO)


def odoo_url() -> str:
    return _texto("MUEBLES_ODOO_URL", f"http://127.0.0.1:{puerto_odoo_host()}")


def odoo_base() -> str:
    return base_de_datos()


def odoo_api_key() -> str:
    valor = os.environ.get("MUEBLES_ODOO_API_KEY", "").strip()
    if not valor:
        raise RuntimeError(
            "Falta MUEBLES_ODOO_API_KEY: la API key del usuario de integración "
            "(grupo «Panel del día: solo lectura»). Ver SECURITY.md."
        )
    return valor


def carpeta_cache() -> Path:
    return CARPETA / "cache_panel"
