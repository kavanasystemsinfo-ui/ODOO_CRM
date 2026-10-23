#!/usr/bin/env python3
"""Cliente JSON-RPC de Odoo para el panel del día (benchmark punto 4).

Reemplaza las consultas SQL directas contra PostgreSQL por llamadas a la API
oficial JSON-RPC de Odoo usando odoorpc (biblioteca oficial de la OCA).

Esto desacopla el panel del esquema interno de la base de datos: actualizaciones
de Odoo (incluyendo cambios de versión) no rompen el panel, porque la API
pública es el contrato estable.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import odoorpc

import configuracion

log = logging.getLogger(__name__)


class OdooClientError(Exception):
    """Excepción cuando el cliente Odoo falla de forma recuperable."""

    pass


@lru_cache(maxsize=1)
def _cliente() -> odoorpc.ODOO:
    """Crea y cachea el cliente JSON-RPC contra Odoo."""
    odoo = odoorpc.ODOO(
        configuracion.odoo_jsonrpc_host(),
        port=configuracion.odoo_jsonrpc_port(),
        protocol="jsonrpc",
    )
    odoo.login(
        configuracion.odoo_jsonrpc_db(),
        configuracion.odoo_jsonrpc_user(),
        configuracion.odoo_jsonrpc_password(),
    )
    return odoo


def _cerrar_cliente() -> None:
    """Olvida la sesión cacheada (caducó o el servidor se reinició)."""
    _cliente.cache_clear()


def _ejecutar(modelo: str, metodo: str, *args, **kwargs) -> Any:
    """Ejecuta un método en un modelo de Odoo con manejo de errores.

    La sesión de Odoo caduca: si eso pasa, se abre una sesión nueva y se
    reintenta una vez. Sin ese reintento, el primer fallo dejaría el panel
    sin datos hasta el siguiente reinicio del servicio.
    """
    try:
        cliente = _cliente()
        return cliente.execute_kw(modelo, metodo, args, kwargs)
    except odoorpc.error.RPCError as exc:
        mensaje = str(exc).lower()
        if "session" in mensaje or "expired" in mensaje or "invalid" in mensaje:
            try:
                _cerrar_cliente()
                cliente = _cliente()
                return cliente.execute_kw(modelo, metodo, args, kwargs)
            except Exception as exc_retry:  # noqa: BLE001
                raise OdooClientError(
                    f"Odoo RPC error en {modelo}.{metodo}: {exc_retry}") from exc_retry
        raise OdooClientError(f"Odoo RPC error en {modelo}.{metodo}: {exc}") from exc
    except ConnectionError as exc:
        raise OdooClientError(
            f"No se puede conectar a Odoo JSON-RPC en "
            f"{configuracion.odoo_jsonrpc_host()}:{configuracion.odoo_jsonrpc_port()}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise OdooClientError(f"Error inesperado en {modelo}.{metodo}: {exc}") from exc


def _buscar(modelo: str, dominio: list, campos: list[str] | None = None, **kwargs) -> list:
    """Busca y lee registros (search_read)."""
    return _ejecutar(modelo, "search_read", dominio, campos or [], **kwargs)


def _contar(modelo: str, dominio: list) -> int:
    """Cuenta registros (search_count)."""
    return _ejecutar(modelo, "search_count", dominio)


def _leer(modelo: str, ids: list[int], campos: list[str]) -> list:
    """Lee registros por IDs (read)."""
    return _ejecutar(modelo, "read", ids, campos)


# ---------------------------------------------------------------------------
# Funciones de alto nivel que reemplazan las consultas SQL de panel_muebles.py
# ---------------------------------------------------------------------------

CATALOGO_DOMINIO = [("categ_id.complete_name", "=ilike", "Muebles de Hogar%")]


def productos_publicados() -> int:
    return _contar("product.template", [("is_published", "=", True)])


def productos_activos() -> int:
    return _contar("product.template", [("active", "=", True)])


def productos_modelo_propio() -> int:
    return _contar("furniture.product", [])


def clientes() -> int:
    return _contar("res.partner", [("customer_rank", ">", 0)])


def proveedores() -> int:
    return _contar("res.partner", [("supplier_rank", ">", 0)])


def pedidos_totales() -> int:
    return _contar("sale.order", [])


def pedidos_confirmados() -> int:
    return _contar("sale.order", [("state", "=", "sale")])


def pedidos_presupuesto() -> int:
    return _contar("sale.order", [("state", "in", ["draft", "sent"])])


def pedidos_cancelados() -> int:
    return _contar("sale.order", [("state", "=", "cancel")])


def entregas_hechas() -> int:
    return _contar(
        "stock.picking",
        [("picking_type_id.code", "=", "outgoing"), ("state", "=", "done")],
    )


def entregas_pendientes() -> int:
    return _contar(
        "stock.picking",
        [("picking_type_id.code", "=", "outgoing"), ("state", "not in", ["done", "cancel"])],
    )


def recepciones_hechas() -> int:
    return _contar(
        "stock.picking",
        [("picking_type_id.code", "=", "incoming"), ("state", "=", "done")],
    )


def recepciones_pendientes() -> int:
    return _contar(
        "stock.picking",
        [("picking_type_id.code", "=", "incoming"), ("state", "not in", ["done", "cancel"])],
    )


def compras_totales() -> int:
    return _contar("purchase.order", [])


def compras_pendientes() -> int:
    # Pedidos de compra con líneas que tienen movimientos no terminados
    ordenes = _buscar(
        "purchase.order.line",
        [("move_ids.state", "not in", ["done", "cancel"])],
        ["order_id"],
    )
    return len({o["order_id"][0] for o in ordenes if o.get("order_id")})


def asientos_contables() -> int:
    return _contar("account.move", [])


def existencias_catalogo() -> int:
    """Unidades en stock interno de productos del catálogo."""
    quants = _buscar(
        "stock.quant",
        [("location_id.usage", "=", "internal"), ("quantity", ">", 0), ("product_id.categ_id.complete_name", "=ilike", "Muebles de Hogar%")],
        ["quantity"],
    )
    return int(round(sum(q["quantity"] for q in quants)))


def referencias_con_stock() -> int:
    """Referencias distintas con stock > 0 en ubicaciones internas del catálogo."""
    quants = _buscar(
        "stock.quant",
        [("location_id.usage", "=", "internal"), ("quantity", ">", 0), ("product_id.categ_id.complete_name", "=ilike", "Muebles de Hogar%")],
        ["product_id"],
    )
    return len({q["product_id"][0] for q in quants if q.get("product_id")})


def valor_almacen() -> float:
    """Valoración del almacén: existencias x coste estándar.

    Por qué: los apuntes de valoración (stock.valuation.layer) no existen en
    esta edición, así que esa vía daría 0 y el panel publicaría una cifra
    falsa. El coste estándar está en el catálogo y es determinista: cada
    lector puede reproducir la cifra con una consulta.
    """
    try:
        quants = _buscar("stock.quant", [["location_id.usage", "=", "internal"],
                                         ["quantity", ">", 0]],
                         ["quantity", "product_id"])
        if not quants:
            return 0.0
        productos = _buscar("product.product", [["id", "in",
                                                 [q["product_id"][0] for q in quants]]],
                            ["standard_price"])
        coste = {p["id"]: p["standard_price"] or 0 for p in productos}
        return round(sum(q["quantity"] * coste.get(q["product_id"][0], 0)
                         for q in quants), 2)
    except OdooClientError:
        # Sin acceso a las existencias: 0.0 indica que no se pudo valorar.
        return 0.0


def traza_existencias_movimientos() -> dict:
    """Trazabilidad del almacén: unidades con al menos un movimiento hecho.

    Misma métrica que la versión SQL-directo del panel: no se compara la suma
    de movimientos con el stock (en esta demo no cuadra porque el almacén se
    sembró con un ajuste y hay transferencias internas), sino si cada
    referencia con existencias tiene movimientos hechos registrados.
    """
    quants = _buscar(
        "stock.quant",
        [["location_id.usage", "=", "internal"], ["quantity", ">", 0]],
        ["quantity", "product_id"],
    )
    existencias_por_producto: dict[int, float] = {}
    for quant in quants:
        producto = quant["product_id"][0]
        existencias_por_producto[producto] = (
            existencias_por_producto.get(producto, 0) + quant["quantity"]
        )
    movidos: set[int] = set()
    for campo in ("location_id.usage", "location_dest_id.usage"):
        lineas = _buscar(
            "stock.move.line",
            [["state", "=", "done"], [campo, "=", "internal"]],
            ["product_id"],
        )
        for linea in lineas:
            movidos.add(linea["product_id"][0])
    trazados = {p for p in existencias_por_producto if p in movidos}
    return {
        "productos": len(existencias_por_producto),
        "productos_trazados": len(trazados),
        "unidades": int(round(sum(existencias_por_producto.values()))),
        "unidades_trazadas": int(round(sum(existencias_por_producto[p] for p in trazados))),
    }


def lineas_fuera_catalogo() -> int:
    """Líneas de pedido que apuntan a productos fuera del catálogo."""
    # Buscar líneas cuyo product_id no está en el catálogo
    lineas = _buscar(
        "sale.order.line",
        [("product_id.categ_id.complete_name", "not ilike", "Muebles de Hogar%")],
        ["id"],
    )
    return len(lineas)


def actividad_dias_max_presupuesto() -> int:
    """Días máximos de antigüedad de presupuestos (draft/sent)."""
    # Odoo no permite MAX en search_read fácilmente; leer y calcular en Python
    pedidos = _buscar(
        "sale.order",
        [("state", "in", ["draft", "sent"])],
        ["date_order"],
    )
    if not pedidos:
        return 0
    from datetime import date, datetime
    hoy = date.today()
    return max((hoy - datetime.strptime(p["date_order"], "%Y-%m-%d %H:%M:%S").date()).days for p in pedidos)


def presupuestos_viejos() -> int:
    """Presupuestos con más de 7 días."""
    pedidos = _buscar(
        "sale.order",
        [("state", "in", ["draft", "sent"])],
        ["date_order"],
    )
    if not pedidos:
        return 0
    from datetime import date, datetime
    hace_7 = date.fromordinal(date.today().toordinal() - 6)
    return sum(1 for p in pedidos if datetime.strptime(p["date_order"], "%Y-%m-%d %H:%M:%S").date() < hace_7)


def actividades_totales() -> int:
    return _contar("mail.activity", [])


def actividades_vencidas() -> int:
    from datetime import date
    return _contar("mail.activity", [("date_deadline", "<", date.today().isoformat())])


def actividades_hoy() -> int:
    from datetime import date
    return _contar("mail.activity", [("date_deadline", "=", date.today().isoformat())])


def actividades_manana() -> int:
    from datetime import date
    manana = date.fromordinal(date.today().toordinal() + 1)
    return _contar("mail.activity", [("date_deadline", "=", manana.isoformat())])


def actividades_proximas() -> int:
    from datetime import date
    manana = date.fromordinal(date.today().toordinal() + 1)
    return _contar("mail.activity", [("date_deadline", ">", manana.isoformat())])


def prioridades_actividades() -> list[dict]:
    """Top 4 actividades vencidas o de hoy/mañana con usuario y resumen."""
    from datetime import date
    hoy = date.today()
    manana = date.fromordinal(hoy.toordinal() + 1)
    actividades = _buscar(
        "mail.activity",
        [
            ("date_deadline", "<=", manana.isoformat()),
            ("user_id", "!=", False),
        ],
        ["user_id", "summary", "res_model", "res_id", "date_deadline"],
        order="date_deadline",
        limit=4,
    )
    res = []
    for a in actividades:
        login = a["user_id"][1].split("@")[0] if a.get("user_id") else "?"
        res.append(
            {
                "tipo": "actividad",
                "etiqueta": login,
                "texto": f"{a['summary']} ({a['res_model']} #{a['res_id']})",
                "urgente": a["date_deadline"] <= hoy.isoformat(),
            }
        )
    return res


def prioridades_entregas() -> list[dict]:
    """Top 3 entregas pendientes preparadas."""
    entregas = _buscar(
        "stock.picking",
        [("picking_type_id.code", "=", "outgoing"), ("state", "not in", ["done", "cancel"])],
        ["name", "partner_id", "sale_id", "scheduled_date"],
        order="scheduled_date",
        limit=3,
    )
    res = []
    for d in entregas:
        cliente = d["partner_id"][1] if d.get("partner_id") else (d["sale_id"][1] if d.get("sale_id") else "(sin cliente)")
        res.append(
            {"tipo": "entrega", "etiqueta": d["name"], "texto": f"Entrega preparada para {cliente}", "urgente": False}
        )
    return res


def prioridades_recepciones() -> list[dict]:
    """Top 3 recepciones pendientes."""
    recepciones = _buscar(
        "stock.picking",
        [("picking_type_id.code", "=", "incoming"), ("state", "not in", ["done", "cancel"])],
        ["name", "partner_id", "scheduled_date"],
        order="scheduled_date",
        limit=3,
    )
    res = []
    for r in recepciones:
        proveedor = r["partner_id"][1] if r.get("partner_id") else "(sin proveedor)"
        res.append(
            {"tipo": "recepción", "etiqueta": r["name"], "texto": f"Recepción pendiente de {proveedor}", "urgente": False}
        )
    return res


def evolutivo_entregas() -> dict[str, int]:
    """Entregas hechas: hoy, ayer, últimos 7 días."""
    from datetime import date

    hoy = date.today()
    ayer = date.fromordinal(hoy.toordinal() - 1)
    hace_7 = date.fromordinal(hoy.toordinal() - 6)

    def hechas(desde: date, hasta: date) -> int:
        return _contar(
            "stock.picking",
            [
                ("picking_type_id.code", "=", "outgoing"),
                ("state", "=", "done"),
                ("date_done", ">=", desde.isoformat()),
                ("date_done", "<=", hasta.isoformat()),
            ],
        )

    return {
        "entregas_hoy": hechas(hoy, hoy),
        "entregas_ayer": hechas(ayer, ayer),
        "entregas_semana": hechas(hace_7, hoy),
    }


def evolutivo_recepciones() -> dict[str, int]:
    """Recepciones hechas: hoy, ayer, últimos 7 días."""
    from datetime import date

    hoy = date.today()
    ayer = date.fromordinal(hoy.toordinal() - 1)
    hace_7 = date.fromordinal(hoy.toordinal() - 6)

    def hechas(desde: date, hasta: date) -> int:
        return _contar(
            "stock.picking",
            [
                ("picking_type_id.code", "=", "incoming"),
                ("state", "=", "done"),
                ("date_done", ">=", desde.isoformat()),
                ("date_done", "<=", hasta.isoformat()),
            ],
        )

    return {
        "recepciones_hoy": hechas(hoy, hoy),
        "recepciones_ayer": hechas(ayer, ayer),
        "recepciones_semana": hechas(hace_7, hoy),
    }


# ---------------------------------------------------------------------------
# Función de prueba de conexión
# ---------------------------------------------------------------------------

def probar_conexion() -> tuple[bool, str]:
    """Prueba la conexión JSON-RPC y devuelve (ok, mensaje)."""
    try:
        cliente = _cliente()
        version = cliente.version
        return True, f"Odoo {version.get('server_version', '?')} conectado via JSON-RPC"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)