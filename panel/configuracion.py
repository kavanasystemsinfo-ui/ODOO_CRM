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

# Configuración del cliente JSON-RPC (benchmark punto 4)
ODOO_JSONRPC_HOST_POR_DEFECTO = "127.0.0.1"
ODOO_JSONRPC_PORT_POR_DEFECTO = 8070
ODOO_JSONRPC_DB_POR_DEFECTO = "furniture_db"
# Usuario y password SIN default: obligatorios por variable de entorno
# MUEBLES_JSONRPC_USER y MUEBLES_JSONRPC_PASSWORD


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


def odoo_jsonrpc_host() -> str:
    return _texto("MUEBLES_JSONRPC_HOST", ODOO_JSONRPC_HOST_POR_DEFECTO)


def odoo_jsonrpc_port() -> int:
    return int(_texto("MUEBLES_JSONRPC_PORT", str(ODOO_JSONRPC_PORT_POR_DEFECTO)))


def odoo_jsonrpc_db() -> str:
    return _texto("MUEBLES_JSONRPC_DB", ODOO_JSONRPC_DB_POR_DEFECTO)


def odoo_jsonrpc_user() -> str:
    # Sin default: obligatorio definir MUEBLES_JSONRPC_USER en el entorno
    valor = os.environ.get("MUEBLES_JSONRPC_USER", "").strip()
    if not valor:
        raise RuntimeError("Variable de entorno MUEBLES_JSONRPC_USER no definida")
    return valor


def odoo_jsonrpc_password() -> str:
    # Sin default: obligatorio definir MUEBLES_JSONRPC_PASSWORD en el entorno
    valor = os.environ.get("MUEBLES_JSONRPC_PASSWORD", "").strip()
    if not valor:
        raise RuntimeError("Variable de entorno MUEBLES_JSONRPC_PASSWORD no definida")
    return valor


def carpeta_cache() -> Path:
    return CARPETA / "cache_panel"
