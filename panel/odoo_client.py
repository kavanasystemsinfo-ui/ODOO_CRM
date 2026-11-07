#!/usr/bin/env python3
"""Lectura del laboratorio a través de la API externa de Odoo (JSON-2).

Por qué así y no con SQL: Odoo no es solo una base de datos. Permisos por
grupo, reglas de registro, campos calculados (el score comercial no existe
como columna) y multiempresa viven en el ORM; una consulta SQL se los salta.
Hasta la v1 el panel leía PostgreSQL con usuario y contraseña fijos aunque la
documentación decía lo contrario. Ahora solo hay un camino:

    POST {url}/json/2/{modelo}/{método}
    Authorization: bearer <API key del usuario de integración>

- El usuario de integración solo tiene el grupo «Panel del día: solo lectura»
  del módulo: si el panel intentase escribir, Odoo respondería 403.
- La API key va en el entorno (MUEBLES_ODOO_API_KEY), nunca en el código.
- Sin dependencias: librería estándar (urllib + json).

Las funciones de lectura reproducen las cifras que publicaba la versión SQL
(mismos estados y umbrales) para que el panel no cambie de significado.
Cuando la versión SQL contaba algo que el ORM no considera vigente (registros
archivados, líneas de sección sin producto), se sigue el criterio del ORM.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Callable

import configuracion

# Estados de albarán que la versión SQL contaba como "pendientes".
ESTADOS_PICKING_PENDIENTE = ["assigned", "waiting", "confirmed"]
ESTADOS_PICKING_PRIORIDAD = ["assigned", "waiting"]
ESTADOS_COMPRA_PENDIENTE = ["draft", "sent", "to approve"]
DIAS_PRESUPUESTO_VIEJO = 30
ETIQUETAS_MODELO = {
    "sale.order": "Pedido", "purchase.order": "Compra", "stock.picking": "Albarán",
    "account.move": "Asiento", "crm.lead": "Oportunidad",
}


class OdooClientError(Exception):
    """La API de Odoo no respondió o respondió con un error."""


# ---------------------------------------------------------------------------
# Transporte
# ---------------------------------------------------------------------------

class OdooJson2:
    """Cliente mínimo de la API JSON-2 de Odoo (Odoo 19 o posterior)."""

    def __init__(self, url: str, base: str, clave: str, timeout: float = 30.0):
        self.url = url.rstrip("/")
        self.base = base
        self.clave = clave
        self.timeout = timeout

    def __call__(self, modelo: str, metodo: str, **parametros: Any) -> Any:
        peticion = urllib.request.Request(
            f"{self.url}/json/2/{modelo}/{metodo}",
            data=json.dumps(parametros).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"bearer {self.clave}",
                "X-Odoo-Database": self.base,
                "User-Agent": "kavana-panel-muebles/2.0",
            },
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self.timeout) as respuesta:
                return json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OdooClientError(
                f"{modelo}.{metodo}: HTTP {exc.code} {_mensaje_de_error(exc)}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise OdooClientError(f"sin conexión con Odoo en {self.url}: {exc}") from exc


def _mensaje_de_error(exc: urllib.error.HTTPError) -> str:
    """Solo el mensaje: la traza que Odoo adjunta no se reenvía al visitante."""
    try:
        return json.loads(exc.read().decode("utf-8")).get("message", "")
    except Exception:  # noqa: BLE001
        return exc.reason or ""


Ejecutor = Callable[..., Any]
_ejecutor: Ejecutor | None = None


def usar(ejecutor: Ejecutor | None) -> None:
    """Fija el ejecutor (las pruebas inyectan uno falso; None = el del entorno)."""
    global _ejecutor
    _ejecutor = ejecutor


def _llamar(modelo: str, metodo: str, **parametros: Any) -> Any:
    global _ejecutor
    if _ejecutor is None:
        _ejecutor = OdooJson2(configuracion.odoo_url(), configuracion.odoo_base(),
                              configuracion.odoo_api_key())
    return _ejecutor(modelo, metodo, **parametros)


def _contar(modelo: str, dominio: list) -> int:
    return int(_llamar(modelo, "search_count", domain=dominio))


def _buscar(modelo: str, dominio: list, campos: list[str], **opciones: Any) -> list[dict]:
    return _llamar(modelo, "search_read", domain=dominio, fields=campos, **opciones)


def _hoy() -> date:
    return date.today()


def _fecha(valor: str | bool) -> date | None:
    if not valor:
        return None
    return datetime.fromisoformat(str(valor)).date()


def _nombre(valor: Any, por_defecto: str = "") -> str:
    """Nombre de un many2one tal como llega por la API ([id, nombre] o False)."""
    if isinstance(valor, (list, tuple)) and len(valor) > 1:
        return str(valor[1])
    return por_defecto


# ---------------------------------------------------------------------------
# Catálogo, terceros y pedidos
# ---------------------------------------------------------------------------

def productos_activos() -> int:
    return _contar("product.template", [("active", "=", True)])


def productos_publicados() -> int:
    return _contar("product.template", [("is_published", "=", True)])


def productos_con_ficha() -> int:
    """Productos nativos con ficha de mobiliario (sustituye al modelo propio v1)."""
    return _contar("product.template", [("furniture_material", "!=", False)])


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


def compras_totales() -> int:
    return _contar("purchase.order", [])


def compras_pendientes() -> int:
    return _contar("purchase.order", [("state", "in", ESTADOS_COMPRA_PENDIENTE)])


def asientos_contables() -> int:
    return _contar("account.move", [("state", "=", "posted")])


# ---------------------------------------------------------------------------
# Almacén
# ---------------------------------------------------------------------------

def _albaranes(codigo: str, estados: list[str]) -> int:
    return _contar("stock.picking", [("picking_type_id.code", "=", codigo),
                                     ("state", "in", estados)])


def entregas_hechas() -> int:
    return _albaranes("outgoing", ["done"])


def entregas_pendientes() -> int:
    return _albaranes("outgoing", ESTADOS_PICKING_PENDIENTE)


def recepciones_hechas() -> int:
    return _albaranes("incoming", ["done"])


def recepciones_pendientes() -> int:
    return _albaranes("incoming", ESTADOS_PICKING_PENDIENTE)


def _existencias_internas(solo_positivas: bool = True) -> list[dict]:
    dominio = [("location_id.usage", "=", "internal")]
    if solo_positivas:
        dominio.append(("quantity", ">", 0))
    return _buscar("stock.quant", dominio, ["product_id", "quantity"])


def referencias_con_stock() -> int:
    return len({q["product_id"][0] for q in _existencias_internas() if q.get("product_id")})


def existencias_catalogo() -> int:
    return int(sum(q["quantity"] for q in _existencias_internas()))


def valor_almacen() -> float:
    """Existencias internas a coste estándar (esta edición no tiene apuntes de valoración).

    standard_price depende de la empresa. La versión SQL leía la clave '1' del
    jsonb (la empresa con id 1); la API devuelve el coste de la empresa activa
    del usuario de integración. Con una sola empresa, como en el laboratorio,
    es la misma cifra; con varias habría que fijar la empresa en el contexto.
    """
    quants = _existencias_internas(solo_positivas=False)
    ids = sorted({q["product_id"][0] for q in quants if q.get("product_id")})
    if not ids:
        return 0.0
    coste = {p["id"]: p["standard_price"] or 0.0
             for p in _buscar("product.product", [("id", "in", ids)], ["standard_price"])}
    return round(sum(q["quantity"] * coste.get(q["product_id"][0], 0.0)
                     for q in quants if q.get("product_id")), 2)


def traza_existencias_movimientos() -> dict:
    """Unidades en almacén respaldadas por al menos un movimiento hecho.

    No se compara la suma de movimientos con el stock (en esta demo no cuadra:
    el almacén se sembró con un ajuste y hay transferencias internas); se mira
    si cada referencia con existencias tiene movimientos hechos registrados.
    """
    por_producto: dict[int, float] = {}
    for quant in _existencias_internas():
        producto = quant["product_id"][0]
        por_producto[producto] = por_producto.get(producto, 0.0) + quant["quantity"]
    movidos: set[int] = set()
    for campo in ("location_id.usage", "location_dest_id.usage"):
        for linea in _buscar("stock.move.line", [("state", "=", "done"), (campo, "=", "internal")],
                             ["product_id"]):
            if linea.get("product_id"):
                movidos.add(linea["product_id"][0])
    trazados = [p for p in por_producto if p in movidos]
    return {
        "productos": len(por_producto),
        "productos_trazados": len(trazados),
        "unidades": int(sum(por_producto.values())),
        "unidades_trazadas": int(sum(por_producto[p] for p in trazados)),
    }


def lineas_fuera_catalogo() -> int:
    """Líneas de venta con producto que no cuelga de «Muebles de Hogar».

    La versión SQL comparaba con el id 127 escrito a mano; ahora se usa el
    campo is_furniture del módulo, que sigue a la categoría aunque cambie de id.
    """
    return _contar("sale.order.line", [("product_id", "!=", False),
                                       ("product_id.is_furniture", "=", False)])


def _presupuestos_borrador() -> list[dict]:
    return _buscar("sale.order", [("state", "=", "draft")], ["date_order"])


def actividad_dias_max_presupuesto() -> int:
    hoy = _hoy()
    dias = [(hoy - _fecha(p["date_order"])).days for p in _presupuestos_borrador()
            if p.get("date_order")]
    return max([0, *dias])


def presupuestos_viejos() -> int:
    limite = _hoy() - timedelta(days=DIAS_PRESUPUESTO_VIEJO)
    return sum(1 for p in _presupuestos_borrador()
               if p.get("date_order") and _fecha(p["date_order"]) <= limite)


# ---------------------------------------------------------------------------
# Actividades
# ---------------------------------------------------------------------------

def actividades_totales() -> int:
    return _contar("mail.activity", [])


def actividades_vencidas() -> int:
    return _contar("mail.activity", [("date_deadline", "<", _hoy().isoformat())])


def actividades_hoy() -> int:
    return _contar("mail.activity", [("date_deadline", "=", _hoy().isoformat())])


def actividades_manana() -> int:
    manana = _hoy() + timedelta(days=1)
    return _contar("mail.activity", [("date_deadline", "=", manana.isoformat())])


def actividades_proximas() -> int:
    manana = _hoy() + timedelta(days=1)
    return _contar("mail.activity", [("date_deadline", ">", manana.isoformat())])


# ---------------------------------------------------------------------------
# Bandeja de prioridades y evolución
# ---------------------------------------------------------------------------

def prioridades_actividades() -> list[dict]:
    """Actividades vencidas y de hoy (las 10 más antiguas)."""
    hoy = _hoy()
    filas = _buscar(
        "mail.activity", [("date_deadline", "<=", hoy.isoformat())],
        ["summary", "activity_type_id", "date_deadline", "user_id", "res_model", "res_id"],
        order="date_deadline", limit=10,
    )
    resultado = []
    for fila in filas:
        etiqueta = ETIQUETAS_MODELO.get(fila["res_model"], fila["res_model"])
        resumen = fila.get("summary") or _nombre(fila.get("activity_type_id"), "actividad")
        persona = _nombre(fila.get("user_id"), "sin asignar")
        resultado.append({
            "tipo": "Actividad",
            "texto": f"{etiqueta} {fila['res_id']} — {resumen} ({persona})",
            "urgente": _fecha(fila["date_deadline"]) < hoy,
        })
    return resultado


def _prioridades_albaranes(codigo: str, origen: str, tipo: str, rol: str) -> list[dict]:
    fin_de_hoy = f"{_hoy().isoformat()} 23:59:59"
    filas = _buscar(
        "stock.picking",
        [("picking_type_id.code", "=", codigo), ("state", "in", ESTADOS_PICKING_PRIORIDAD),
         ("scheduled_date", "<=", fin_de_hoy), (origen, "!=", False)],
        ["name", "partner_id", "scheduled_date"], order="scheduled_date", limit=10,
    )
    return [{
        "tipo": tipo,
        "texto": f"{f['name']} — {rol} {_nombre(f.get('partner_id'), '(sin nombre)')} "
                 f"(prevista {f['scheduled_date']})",
        "urgente": False,
    } for f in filas]


def prioridades_entregas() -> list[dict]:
    return _prioridades_albaranes("outgoing", "sale_id", "Entrega", "cliente")


def prioridades_recepciones() -> list[dict]:
    return _prioridades_albaranes("incoming", "purchase_id", "Recepción", "proveedor")


def _hechos_desde(codigo: str, desde: date, hasta: date) -> int:
    return _contar("stock.picking", [
        ("picking_type_id.code", "=", codigo), ("state", "=", "done"),
        ("date_done", ">=", f"{desde.isoformat()} 00:00:00"),
        ("date_done", "<=", f"{hasta.isoformat()} 23:59:59"),
    ])


def _evolutivo(codigo: str, prefijo: str) -> dict[str, int]:
    hoy = _hoy()
    ayer = hoy - timedelta(days=1)
    return {
        f"{prefijo}_hoy": _hechos_desde(codigo, hoy, hoy),
        f"{prefijo}_ayer": _hechos_desde(codigo, ayer, ayer),
        f"{prefijo}_semana": _hechos_desde(codigo, hoy - timedelta(days=7), hoy),
    }


def evolutivo_entregas() -> dict[str, int]:
    return _evolutivo("outgoing", "entregas")


def evolutivo_recepciones() -> dict[str, int]:
    return _evolutivo("incoming", "recepciones")


# ---------------------------------------------------------------------------
# CRM: el score lo calcula el módulo en Odoo; el panel solo lo lee
# ---------------------------------------------------------------------------

CAMPOS_SENALES = {
    "tipo_contrato": "x_es_contrato",
    "proyecto_referenciado": "x_proyecto_referenciado",
    "muestra_pedida": "x_muestra_pedida",
    "email_corporativo": "x_email_corporativo",
    "contacto_reciente": "x_contacto_reciente",
}


def oportunidades_crm() -> list[dict]:
    """Leads y oportunidades activos con el score y las señales del módulo."""
    campos = ["name", "x_score_kavana", "x_prioridad_sugerida", *CAMPOS_SENALES.values()]
    return _buscar("crm.lead", [], campos)


def mejor_oportunidad() -> dict | None:
    """La oportunidad con más score (a igualdad, la de id menor)."""
    filas = oportunidades_crm()
    if not filas:
        return None
    mejor = max(filas, key=lambda f: (f.get("x_score_kavana") or 0, -f["id"]))
    return {
        "id": mejor["id"],
        "nombre": mejor["name"],
        "score_kavana": mejor.get("x_score_kavana") or 0,
        "prioridad_sugerida": mejor.get("x_prioridad_sugerida") or "ninguna",
        "senales": {senal: bool(mejor.get(campo)) for senal, campo in CAMPOS_SENALES.items()},
    }


def probar_conexion() -> tuple[bool, str]:
    try:
        return True, f"API de Odoo accesible: {productos_activos()} productos activos"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
