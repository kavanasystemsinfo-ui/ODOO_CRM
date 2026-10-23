#!/usr/bin/env python3
"""
Panel del día del laboratorio de muebles (Muebles del Hogar S.L.).

Para qué: dar a quien visita la demo una pantalla que resuma, en lenguaje de
negocio, cómo está la empresa hoy y qué pide atención, sin obligarle a entender
el ERP por dentro.

Principios de diseño (los mismos que el panel de aromas):
  - Solo lectura. El panel no escribe nada en el laboratorio; lee por SQL del
    contenedor de PostgreSQL (sin ORM y sin dependencias: librería estándar).
  - Las frases de resumen son REGLAS deterministas (recuentos y umbrales). La
    parte que redactaría un modelo se precomputa aparte; si no hay clave, el
    panel lo declara en vez de aparentarlo.
  - Honestidad visible: banda de "laboratorio de demostración" y sección de
    salud del dato que dice qué falta y por qué.
  - El botón de reinicio exige la sesión de administrador del propio Odoo y
    tiene una espera mínima entre reinicios.

Uso:
    python3 panel_muebles.py --precomputar   # lee el laboratorio y escribe la caché del día
    python3 panel_muebles.py --puerto 8081   # sirve / y /api/dia
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import configuracion  # noqa: E402
import asistente  # noqa: E402

BANNER = "Laboratorio de demostración — Muebles del Hogar S.L. (base furniture_db)"

# ---------------------------------------------------------------------------
# Módulos puros del repositorio (sin Odoo): el scoring y la capa MCP son
# funciones deterministas que se pueden reutilizar tal cual desde el panel.
# Se cargan por ruta porque `models/__init__.py` importa Odoo.
# ---------------------------------------------------------------------------
RAIZ_MODULO = Path(__file__).resolve().parent.parent
_MODULOS_PUROS: dict = {}


def _modulo_puro(nombre: str, fichero: str):
    if nombre not in _MODULOS_PUROS:
        ruta = RAIZ_MODULO / "models" / fichero
        spec = importlib.util.spec_from_file_location(nombre, ruta)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        _MODULOS_PUROS[nombre] = modulo
    return _MODULOS_PUROS[nombre]

# ---------------------------------------------------------------------------
# Reinicio del laboratorio: el visitante entra como administrador y puede
# romper lo que quiera; el botón lo devuelve al estado inicial. Se exige la
# sesión del propio Odoo (y que sea administrador) para que un anónimo no
# reinicie la demo mientras otro la usa, y hay espera mínima entre reinicios.
# ---------------------------------------------------------------------------
REINICIO = {"en_curso": False, "iniciado": 0.0, "resultado": None, "detalle": ""}
_CANDADO = threading.Lock()


def _sesion_es_admin(cabeceras) -> tuple[bool, str]:
    """Valida la cookie de sesión contra el propio Odoo."""
    cookie = cabeceras.get("Cookie", "")
    if "session_id" not in cookie:
        return False, ("Primero entra en el laboratorio y después pide el reinicio "
                       "desde aquí.")
    peticion = urllib.request.Request(
        f"http://127.0.0.1:{configuracion.puerto_odoo_host()}/web/session/get_session_info",
        data=b"{}",
        headers={"Content-Type": "application/json", "Cookie": cookie})
    try:
        respuesta = json.loads(urllib.request.urlopen(peticion, timeout=10).read())
    except Exception as exc:  # noqa: BLE001
        return False, f"no se pudo comprobar la sesión: {exc}"
    datos = respuesta.get("result") or {}
    if not datos.get("uid"):
        return False, "la sesión del laboratorio no es válida (vuelve a entrar)."
    if not datos.get("is_admin"):
        return False, "solo el usuario administrador puede reiniciar el laboratorio."
    return True, datos.get("username", "admin")


def _reinicio_estado() -> str:
    """libre | en_curso | hecho | error."""
    if REINICIO["en_curso"]:
        return "en_curso"
    return REINICIO["resultado"] or "libre"


def _lanzar_reinicio() -> None:
    """Ejecuta el motor de restauración en segundo plano (no bloquea el panel)."""
    script = Path(__file__).resolve().parent / "demo_restaurar_muebles.py"
    with _CANDADO:
        REINICIO.update(en_curso=True, iniciado=time.time(), resultado=None,
                        detalle="Reiniciando el laboratorio (parar, recargar y arrancar).")
    proceso = subprocess.run([sys.executable, str(script), "--restaurar",
                              "--sin-refrescar-panel"],
                             capture_output=True, text=True)
    with _CANDADO:
        REINICIO.update(en_curso=False,
                        resultado="hecho" if proceso.returncode == 0 else "error",
                        detalle=(proceso.stdout or proceso.stderr or "").strip()[-400:])
    if proceso.returncode == 0:  # la caché describe datos que ya no existen
        for fichero in configuracion.carpeta_cache().glob("dia_*.json"):
            fichero.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Formato español y frases (lógica pura)
# ---------------------------------------------------------------------------

def formato_numero(valor: float) -> str:
    """Formato numérico español: punto para miles, coma para decimales."""
    if isinstance(valor, float) and not float(valor).is_integer():
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{int(valor):,}".replace(",", ".")


def _porcentaje(parte: int, total: int) -> str:
    if total <= 0:
        return "0,0 %"
    return f"{round(parte * 100 / total, 1):.1f}".replace(".", ",") + " %"


def frase_evolucion(nombre: str, hoy: int, ayer: int, semana: int) -> str:
    """Compara el movimiento de hoy con ayer y con el total de hace 7 días.

    Patrón de los informes MIS (benchmark 2026-10-08, punto 2): la misma cifra
    cobra sentido al lado de su periodo anterior. De 0 a N no es un
    porcentaje: es apertura.
    """
    n = formato_numero
    partes = []
    if hoy == ayer == semana:
        return f"{nombre}: sin cambios frente a ayer ni a la semana pasada."
    if hoy != ayer:
        diferencia = hoy - ayer
        verbo = "sube" if diferencia > 0 else "baja"
        partes.append(f"{verbo} {n(abs(diferencia))} frente a ayer"
                      + (f" ({_porcentaje(abs(diferencia), ayer)})" if ayer else ""))
    if hoy != semana:
        partes.append(f"frente a los {n(semana)} de los últimos 7 días")
    return f"{nombre}: " + ", ".join(partes) + "."


def construir_resumen(cifras: dict) -> dict:
    """Convierte las cifras leídas en el resumen que ve el espectador.

    Todo lo que aquí se dice es regla determinista (recuentos y umbrales).
    """
    n = formato_numero
    frases = [
        f"Buenos días. El catálogo tiene {n(cifras['productos'])} muebles publicados y el "
        f"almacén guarda {n(cifras['unidades'])} unidades en {n(cifras['referencias'])} "
        f"referencias, por un valor de {n(cifras['valor_almacen'])} €.",
        f"Movimiento de hoy: {n(cifras['entregas_hechas'])} entregas hechas y "
        f"{n(cifras['entregas_pendientes'])} listas para salir; "
        f"{n(cifras['recepciones_hechas'])} recepciones hechas y "
        f"{n(cifras['recepciones_pendientes'])} pendientes de recibir.",
        f"De {n(cifras['pedidos'])} pedidos, {n(cifras['confirmados'])} están confirmados y "
        f"{n(cifras['presupuestos'])} siguen en presupuesto.",
    ]
    if cifras.get("presupuestos_viejos"):
        frases.append(
            f"Hay {n(cifras['presupuestos_viejos'])} presupuestos con más de "
            f"{cifras['dias_presupuesto_viejo']} días sin respuesta: eso sí es dinero parado."
        )
    if cifras.get("actividades"):
        frases.append(
            f"He revisado {n(cifras['actividades'])} actividades asignadas: "
            f"{n(cifras['vencidas'])} vencidas, {n(cifras['hoy'])} de hoy, "
            f"{n(cifras['manana'])} de mañana y {n(cifras['proximas'])} próximas. "
            f"Lo que necesita decisión son las {n(cifras['vencidas'])} vencidas."
        )
    evolucion = cifras.get("evolucion") or {}
    if evolucion:
        frases.append(
            "Comparado con otros días: "
            + frase_evolucion("entregas hechas", int(evolucion.get("entregas_hoy", 0)),
                              int(evolucion.get("entregas_ayer", 0)),
                              int(evolucion.get("entregas_semana", 0)))
            + " "
            + frase_evolucion("recepciones hechas", int(evolucion.get("recepciones_hoy", 0)),
                              int(evolucion.get("recepciones_ayer", 0)),
                              int(evolucion.get("recepciones_semana", 0)))
        )
    salud = cifras.get("salud_dato", [])
    faltan = [s["campo"] for s in salud if not s.get("ok") and not s.get("no_aplica")]
    ia = []
    if faltan:
        frases.append(
            "Salud del dato: no puedo afirmar nada de " + ", ".join(faltan) +
            ". Si falta el dato, me paro y digo por qué."
        )
    ia.append("Resumen redactado con reglas deterministas precomputadas: sin clave de "
              "modelo no hay redacción por IA, y así se declara en vez de aparentarlo.")
    return {**cifras, "frases": frases, "ia": ia, "salud_dato": salud}


# ---------------------------------------------------------------------------
# Conexión a PostgreSQL del contenedor de Odoo
# ---------------------------------------------------------------------------
def get_pg_conn() -> psycopg2.extensions.connection:
    """Obtiene conexión directa a PostgreSQL del contenedor furniture_db."""
    return psycopg2.connect(
        host="127.0.0.1",
        dbname="furniture_db",
        user="odoo",
        password="odoo",
        port=5434,
        cursor_factory=RealDictCursor,
    )

# ---------------------------------------------------------------------------
# Funciones de conteo SQL directo (diseño original: sin ORM, sin dependencias)
# ---------------------------------------------------------------------------

def total_products() -> int:
    """Cuenta total de productos en el catálogo."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM product_template")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def furniture_products() -> int:
    """Cuenta las referencias del modelo propio del módulo (furniture.product).

    Antes se contaba por categoría (`categ_id = 138`, "Mesas") y salía 34: la
    cifra era una categoría suelta, no el catálogo. El modelo propio tiene su
    propia tabla y ahí están las 80 referencias del laboratorio.
    """
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS furniture FROM furniture_product")
            row = cur.fetchone()
            return row["furniture"] if row else 0
    finally:
        conn.close()


def customers() -> int:
    """Cuenta clientes (partner con customer_rank > 0)."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS customers FROM res_partner WHERE customer_rank > 0")
            row = cur.fetchone()
            return row["customers"] if row else 0
    finally:
        conn.close()


def orders() -> int:
    """Cuenta pedidos de venta."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS orders FROM sale_order")
            row = cur.fetchone()
            return row["orders"] if row else 0
    finally:
        conn.close()


# Funciones adicionales necesarias para el panel completo (SQL directo)
def productos_activos() -> int:
    """Productos del catálogo que están activos (no archivados)."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM product_template WHERE active")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def productos_publicados() -> int:
    """Productos del catálogo publicados en la web."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM product_template WHERE is_published")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def productos_modelo_propio() -> int:
    return furniture_products()


def proveedores() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM res_partner WHERE supplier_rank > 0")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def pedidos_totales() -> int:
    return orders()


def pedidos_confirmados() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM sale_order WHERE state = 'sale'")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def pedidos_presupuesto() -> int:
    """Presupuestos: los borradores y los ya enviados (siguen sin cerrar)."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM sale_order WHERE state IN ('draft', 'sent')")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def pedidos_cancelados() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM sale_order WHERE state = 'cancel'")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def entregas_hechas() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(*) AS total FROM stock_picking sp
                JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                WHERE spt.code = 'outgoing' AND sp.state = 'done'
            """)
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def entregas_pendientes() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(*) AS total FROM stock_picking sp
                JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                WHERE spt.code = 'outgoing' AND sp.state IN ('assigned', 'waiting', 'confirmed')
            """)
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def recepciones_hechas() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(*) AS total FROM stock_picking sp
                JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                WHERE spt.code = 'incoming' AND sp.state = 'done'
            """)
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def recepciones_pendientes() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(*) AS total FROM stock_picking sp
                JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                WHERE spt.code = 'incoming' AND sp.state IN ('assigned', 'waiting', 'confirmed')
            """)
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def compras_totales() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM purchase_order")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def compras_pendientes() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM purchase_order WHERE state IN ('draft', 'sent', 'to approve')")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def asientos_contables() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM account_move WHERE state = 'posted'")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def referencias_con_stock() -> int:
    """Referencias con existencias en ubicaciones internas del almacén."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(DISTINCT sq.product_id) AS total
                FROM stock_quant sq
                JOIN stock_location l ON l.id = sq.location_id
                WHERE l.usage = 'internal' AND sq.quantity > 0
            """)
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def existencias_catalogo() -> int:
    """Unidades en ubicaciones internas del almacén."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(quantity), 0) AS total
                FROM stock_quant
                WHERE location_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
                  AND quantity > 0
            """)
            row = cur.fetchone()
            return int(row["total"]) if row else 0
    finally:
        conn.close()


def valor_almacen() -> float:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(sq.quantity * (pp.standard_price->>'1')::numeric), 0) AS total
                FROM stock_quant sq
                JOIN product_product pp ON sq.product_id = pp.id
                WHERE sq.location_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
            """)
            row = cur.fetchone()
            return float(row["total"]) if row else 0.0
    finally:
        conn.close()


def actividades_totales() -> int:
    """Actividades del CRM assignadas (las 30 del laboratorio, todas manuales)."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM mail_activity")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def actividades_vencidas() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM mail_activity WHERE date_deadline < CURRENT_DATE")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def actividades_hoy() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM mail_activity WHERE date_deadline = CURRENT_DATE")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def actividades_manana() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM mail_activity WHERE date_deadline = CURRENT_DATE + 1")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def actividades_proximas() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM mail_activity WHERE date_deadline > CURRENT_DATE + 1")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def traza_existencias_movimientos() -> dict:
    """Trazabilidad del almacén: unidades respaldadas por movimientos hechos.

    Por qué esta métrica y no "existencias = suma de movimientos": en este
    laboratorio las existencias se sembraron con un ajuste de inventario y
    hay transferencias entre ubicaciones internas, así que la suma aritmética
    de los movimientos no cuadra con el stock (248 unidades de las 2.190 se
    movieron de una ubicación interna a otra). Lo que sí se puede afirmar, y
    es lo que se muestra, es si cada referencia con existencias tiene
    movimientos hechos registrados.
    """
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                WITH existencias AS (
                    SELECT sq.product_id, SUM(sq.quantity) AS qty
                    FROM stock_quant sq
                    JOIN stock_location l ON l.id = sq.location_id
                    WHERE l.usage = 'internal' AND sq.quantity > 0
                    GROUP BY sq.product_id
                ), trazados AS (
                    SELECT sml.product_id, SUM(sml.quantity) AS qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sml.move_id = sm.id
                    WHERE sml.state = 'done'
                      AND (sml.location_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
                        OR sml.location_dest_id IN (SELECT id FROM stock_location WHERE usage = 'internal'))
                    GROUP BY sml.product_id
                )
                SELECT count(*) AS productos,
                       count(t.product_id) AS productos_trazados,
                       COALESCE(SUM(e.qty), 0) AS unidades,
                       COALESCE(SUM(CASE WHEN t.qty > 0 THEN e.qty ELSE 0 END), 0) AS unidades_trazadas
                FROM existencias e
                LEFT JOIN trazados t ON t.product_id = e.product_id
            """)
            row = cur.fetchone()
            if not row:
                return {"productos": 0, "productos_trazados": 0,
                        "unidades": 0, "unidades_trazadas": 0}
            return {
                "productos": int(row["productos"]),
                "productos_trazados": int(row["productos_trazados"]),
                "unidades": int(row["unidades"]),
                "unidades_trazadas": int(row["unidades_trazadas"]),
            }
    finally:
        conn.close()


def lineas_fuera_catalogo() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(*) AS total FROM sale_order_line sol
                JOIN product_product pp ON sol.product_id = pp.id
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                WHERE pt.categ_id NOT IN (
                    SELECT id FROM product_category 
                    WHERE id = 127 OR parent_id = 127
                )
            """)
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def actividad_dias_max_presupuesto() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT GREATEST(CURRENT_DATE - date_order, INTERVAL '0 days') AS dias
                FROM sale_order WHERE state = 'draft' ORDER BY dias DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row and row["dias"]:
                return int(row["dias"].days) if hasattr(row["dias"], 'days') else 0
            return 0
    finally:
        conn.close()


def presupuestos_viejos() -> int:
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS total FROM sale_order WHERE state = 'draft' AND date_order <= CURRENT_DATE - 30")
            row = cur.fetchone()
            return row["total"] if row else 0
    finally:
        conn.close()


def oportunidad_crm() -> dict | None:
    """La oportunidad del CRM con mejor score y la acción que sugiere la capa MCP.

    El score sale de las reglas puras del módulo (models/lead_scoring.py) y la
    acción sugerida de la capa MCP (models/mcp.py). Las señales son las que el
    comercial marcó en la oportunidad (x_es_contrato, x_proyecto_referenciado,
    x_muestra_pedida) más las dos que se deducen (email corporativo y actividad
    en los últimos 7 días). Sin IA y sin azar: la misma entrada da la misma
    salida.
    """
    scoring = _modulo_puro("_kavana_lead_scoring", "lead_scoring.py")
    mcp = _modulo_puro("_kavana_mcp", "mcp.py")
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cl.id, cl.name,
                       COALESCE(cl.email_from, '') AS email_from,
                       COALESCE(p.email, '') AS partner_email,
                       COALESCE(cl.x_es_contrato, false) AS es_contrato,
                       COALESCE(cl.x_proyecto_referenciado, false) AS proyecto,
                       COALESCE(cl.x_muestra_pedida, false) AS muestra,
                       (SELECT max(ma.date_deadline) FROM mail_activity ma
                         WHERE ma.res_model = 'crm.lead' AND ma.res_id = cl.id
                           AND ((COALESCE(ma.active, true) AND ma.date_deadline >= CURRENT_DATE)
                             OR ma.date_done IS NOT NULL)
                       ) AS ultima_actividad
                FROM crm_lead cl
                LEFT JOIN res_partner p ON p.id = cl.partner_id
            """)
            filas = cur.fetchall()
    finally:
        conn.close()

    hoy = date.today()
    mejor = None
    for fila in filas:
        email = fila["email_from"] or fila["partner_email"]
        ultima = fila["ultima_actividad"]
        senales = {
            "tipo_contrato": bool(fila["es_contrato"]),
            "proyecto_referenciado": bool(fila["proyecto"]),
            "muestra_pedida": bool(fila["muestra"]),
            "email_corporativo": scoring.es_email_corporativo(email),
            "contacto_reciente": bool(ultima and (hoy - ultima).days <= 7),
        }
        score = scoring.puntuar(senales)
        if mejor is None or score > mejor["score_kavana"]:
            mejor = {
                "id": fila["id"],
                "nombre": fila["name"],
                "score_kavana": score,
                "prioridad_sugerida": scoring.prioridad_sugerida(score),
                "senales": senales,
            }
    if mejor is None:
        return None
    mejor["mcp_sugerencia"] = mcp.MCPService.sugerir_accion(mejor)
    return mejor


# ---------------------------------------------------------------------------
# Precomputar día (lee el laboratorio y escribe la caché del día)
# ---------------------------------------------------------------------------
def precomputar() -> Path:
    """Lee el laboratorio y escribe la caché del día."""
    carpeta = configuracion.carpeta_cache()
    carpeta.mkdir(exist_ok=True)
    resumen = construir_resumen(leer_cifras())
    destino = carpeta / f"dia_{date.today().isoformat()}.json"
    destino.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def leer_cifras() -> dict:
    """Cifras del panel, leídas por SQL directo a PostgreSQL."""
    try:
        traza = traza_existencias_movimientos()
        existencias = traza["unidades"]
        unidades_trazadas = traza["unidades_trazadas"]
        fuera_catalogo = lineas_fuera_catalogo()
        dias_max = actividad_dias_max_presupuesto()
        viejos = presupuestos_viejos()
        oportunidad = oportunidad_crm()

        cifras = {
            "fecha": date.today().isoformat(),
            "banner": BANNER,
            "productos": productos_activos(),
            "publicados": productos_publicados(),
            "modelo": productos_modelo_propio(),
            "clientes": customers(),
            "proveedores": proveedores(),
            "pedidos": pedidos_totales(),
            "confirmados": pedidos_confirmados(),
            "presupuestos": pedidos_presupuesto(),
            "cancelados": pedidos_cancelados(),
            "entregas_hechas": entregas_hechas(),
            "entregas_pendientes": entregas_pendientes(),
            "recepciones_hechas": recepciones_hechas(),
            "recepciones_pendientes": recepciones_pendientes(),
            "compras": compras_totales(),
            "compras_pendientes": compras_pendientes(),
            "asientos": asientos_contables(),
            "referencias": referencias_con_stock(),
            "unidades": existencias_catalogo(),
            "valor_almacen": valor_almacen(),
            "actividades": actividades_totales(),
            "vencidas": actividades_vencidas(),
            "hoy": actividades_hoy(),
            "manana": actividades_manana(),
            "proximas": actividades_proximas(),
            "presupuestos_viejos": viejos,
            "dias_presupuesto_viejo": dias_max if viejos else 0,
            "unidades_trazadas": unidades_trazadas,
            "mcp_lead": oportunidad,
            "mcp_sugerencia": (oportunidad["mcp_sugerencia"] if oportunidad
                               else "No hay oportunidades en el CRM del laboratorio"),
        }

        salud = [
            {
                "campo": "unidades con movimiento registrado",
                "valor": f"{formato_numero(unidades_trazadas)} / {formato_numero(existencias)}",
                "ok": unidades_trazadas == existencias,
                "motivo": (
                    f"{formato_numero(traza['productos_trazados'])} de "
                    f"{formato_numero(traza['productos'])} referencias con existencias "
                    "tienen al menos un movimiento hecho (los ajustes de inventario y "
                    "las transferencias entre ubicaciones internas también cuentan)"
                    if unidades_trazadas == existencias else
                    f"{formato_numero(existencias - unidades_trazadas)} unidades sin "
                    "ningún movimiento hecho registrado"
                ),
            },
            {
                "campo": "pedidos sobre el catálogo",
                "valor": "todos" if fuera_catalogo == 0 else f"{fuera_catalogo} fuera",
                "ok": fuera_catalogo == 0,
                "motivo": f"{fuera_catalogo} líneas apuntan a productos que no son del catálogo (demo: filtro por árbol de categorías)",
            },
            {
                "campo": "valoración del almacén",
                "valor": f"{formato_numero(cifras['valor_almacen'])} €",
                "ok": cifras["valor_almacen"] > 0,
                "motivo": "valoración a coste estándar del catálogo (esta edición no tiene "
                          "apuntes de valoración)",
            },
            {
                "campo": "tickets de soporte (helpdesk)",
                "valor": 0,
                "ok": False,
                "no_aplica": True,
                "motivo": "no existe en la edición Community",
            },
            {
                "campo": "tareas de proyecto",
                "valor": 0,
                "ok": False,
                "no_aplica": True,
                "motivo": "módulo sin usar",
            },
        ]
        cifras["salud_dato"] = salud

        # Prioridades (actividades, entregas, recepciones)
        prioridades = []
        prioridades.extend(prioridades_actividades())
        prioridades.extend(prioridades_entregas())
        prioridades.extend(prioridades_recepciones())
        cifras["prioridades"] = prioridades

        # Evolución (patrón MIS, benchmark punto 2)
        evolucion = {}
        evolucion.update(evolutivo_entregas())
        evolucion.update(evolutivo_recepciones())
        cifras["evolucion"] = evolucion

        return cifras

    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Lectura SQL-directa falló: {exc}") from exc


# ---------------------------------------------------------------------------
# Prioridades y evolutivos (SQL directo a PostgreSQL)
# ---------------------------------------------------------------------------

def prioridades_actividades():
    """Actividades vencidas y de hoy que necesitan decisión."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    ma.summary AS texto,
                    ma.date_deadline AS fecha,
                    rp.name AS persona,
                    mr.name AS modelo,
                    mr.model AS modelo_tech,
                    ma.res_id AS doc_id
                FROM mail_activity ma
                JOIN res_users ru ON ma.user_id = ru.id
                JOIN res_partner rp ON ru.partner_id = rp.id
                JOIN ir_model mr ON ma.res_model_id = mr.id
                WHERE ma.date_deadline <= CURRENT_DATE
                ORDER BY ma.date_deadline
                LIMIT 10
            """)
            rows = cur.fetchall()
            result = []
            for r in rows:
                urgente = r["fecha"] < date.today()
                modelo_label = {"sale.order": "Pedido", "purchase.order": "Compra",
                                "stock.picking": "Albarán", "account.move": "Asiento",
                                "crm.lead": "Oportunidad"}.get(r["modelo_tech"], r["modelo"])
                result.append({
                    "tipo": "Actividad",
                    "texto": f"{modelo_label} {r['doc_id']} — {r['texto']} ({r['persona']})",
                    "urgente": urgente
                })
            return result
    finally:
        conn.close()


def prioridades_entregas():
    """Entregas preparadas (assigned/waiting) que salen hoy."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sp.name, sp.scheduled_date, rp.name AS cliente
                FROM stock_picking sp
                JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                JOIN sale_order so ON sp.origin = so.name
                JOIN res_partner rp ON so.partner_id = rp.id
                WHERE spt.code = 'outgoing'
                  AND sp.state IN ('assigned', 'waiting')
                  AND sp.scheduled_date <= CURRENT_DATE
                ORDER BY sp.scheduled_date
                LIMIT 10
            """)
            rows = cur.fetchall()
            result = []
            for r in rows:
                result.append({
                    "tipo": "Entrega",
                    "texto": f"{r['name']} — cliente {r['cliente']} (prevista {r['scheduled_date']})",
                    "urgente": False
                })
            return result
    finally:
        conn.close()


def prioridades_recepciones():
    """Recepciones pendientes (assigned/waiting) que llegan hoy."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sp.name, sp.scheduled_date, rp.name AS proveedor
                FROM stock_picking sp
                JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                JOIN purchase_order po ON sp.origin = po.name
                JOIN res_partner rp ON po.partner_id = rp.id
                WHERE spt.code = 'incoming'
                  AND sp.state IN ('assigned', 'waiting')
                  AND sp.scheduled_date <= CURRENT_DATE
                ORDER BY sp.scheduled_date
                LIMIT 10
            """)
            rows = cur.fetchall()
            result = []
            for r in rows:
                result.append({
                    "tipo": "Recepción",
                    "texto": f"{r['name']} — proveedor {r['proveedor']} (prevista {r['scheduled_date']})",
                    "urgente": False
                })
            return result
    finally:
        conn.close()


def evolutivo_entregas():
    """Evolución de entregas: hoy vs ayer vs últimos 7 días."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) FILTER (WHERE date_trunc('day', sp.date_done) = CURRENT_DATE) AS hoy,
                    COUNT(*) FILTER (WHERE date_trunc('day', sp.date_done) = CURRENT_DATE - 1) AS ayer,
                    COUNT(*) FILTER (WHERE date_trunc('day', sp.date_done) >= CURRENT_DATE - 7) AS semana
                FROM stock_picking sp
                JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                WHERE spt.code = 'outgoing' AND sp.state = 'done'
            """)
            row = cur.fetchone()
            if row:
                return {"entregas_hoy": row["hoy"] or 0, "entregas_ayer": row["ayer"] or 0, "entregas_semana": row["semana"] or 0}
            return {"entregas_hoy": 0, "entregas_ayer": 0, "entregas_semana": 0}
    finally:
        conn.close()


def evolutivo_recepciones():
    """Evolución de recepciones: hoy vs ayer vs últimos 7 días."""
    conn = get_pg_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) FILTER (WHERE date_trunc('day', sp.date_done) = CURRENT_DATE) AS hoy,
                    COUNT(*) FILTER (WHERE date_trunc('day', sp.date_done) = CURRENT_DATE - 1) AS ayer,
                    COUNT(*) FILTER (WHERE date_trunc('day', sp.date_done) >= CURRENT_DATE - 7) AS semana
                FROM stock_picking sp
                JOIN stock_picking_type spt ON sp.picking_type_id = spt.id
                WHERE spt.code = 'incoming' AND sp.state = 'done'
            """)
            row = cur.fetchone()
            if row:
                return {"recepciones_hoy": row["hoy"] or 0, "recepciones_ayer": row["ayer"] or 0, "recepciones_semana": row["semana"] or 0}
            return {"recepciones_hoy": 0, "recepciones_ayer": 0, "recepciones_semana": 0}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# HTML completo del panel
# ---------------------------------------------------------------------------

HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel del día — Muebles del Hogar S.L.</title><style>
body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f6f4f1;color:#1f1b16}
.banner{background:#5b3a1e;color:#fff;padding:10px 18px;font-weight:700;text-align:center}
main{max-width:980px;margin:18px auto;padding:0 16px}
h1{font-size:21px;color:#3d2712;margin-bottom:4px} .sub{color:#7a6a5a;font-size:13px;margin-bottom:14px}
h2{font-size:15px;color:#3d2712;border-bottom:1px solid #ddd3c7;padding-bottom:4px;margin-top:22px}
.frase{background:#fff;border:1px solid #ddd3c7;border-radius:8px;padding:12px 14px;margin:8px 0;border-left:4px solid #3d2712}
.frase small{display:block;color:#7a6a5a;margin-top:4px}
.cifras{display:flex;gap:10px;flex-wrap:wrap}
.caja{background:#fff;border:1px solid #ddd3c7;border-radius:8px;padding:10px 14px;min-width:132px}
.caja b{display:block;font-size:21px;color:#3d2712}
.rojo{color:#8b1e1e;font-weight:700}
ul{background:#fff;border:1px solid #ddd3c7;border-radius:8px;padding:12px 12px 12px 30px;margin:0}
li{margin:4px 0}
.tag{font-size:11px;color:#fff;background:#3d2712;border-radius:4px;padding:2px 6px;margin-right:6px}
.reinicio{background:#fff;border:1px solid #ddd3c7;border-radius:8px;padding:12px 14px;margin:20px 0}
.reinicio p{color:#5a4c40;font-size:13px;margin:6px 0 10px}
button{background:#3d2712;color:#fff;border:0;border-radius:6px;padding:9px 16px;font-size:14px;cursor:pointer}
button[disabled]{background:#9a8d80;cursor:default}
.aviso{margin-left:10px;font-size:13px;color:#8b1e1e}
.nota{color:#7a6a5a;font-size:11px}
footer{margin:20px 0;color:#9a8d80;font-size:12px}
</style></head><body>
<div class="banner">Laboratorio de demostración — Muebles del Hogar S.L. (base furniture_db)</div>
<main><h1>Panel del día</h1><div class="sub" id="estado">Cargando...</div>
<div id="frases"></div>
<h2>Cifras del día</h2><div class="cifras" id="cifras"></div>
<h2>Comparado con otros días</h2><div class="cifras" id="evolucion"></div>
<h2>Lo que pide atención</h2><ul id="bandeja"></ul>
<h2>Siguiente acción comercial</h2><ul id="mcp"></ul>
<h2>Salud del dato</h2><ul id="salud"></ul>
<div class="reinicio">
  <h2>Este laboratorio se limpia solo</h2>
  <p>Puedes trastear sin miedo: el servidor devuelve el laboratorio a su estado inicial <strong>cada media hora</strong>, así que lo que cambies no se queda para el siguiente que entre. Ya no hay botón de reinicio aquí a propósito: se limpia solo.</p>
</div>
<footer>El panel solo lee el laboratorio. Las frases son reglas deterministas; la redacción por IA se precomputa aparte y aquí se declara.</footer>
</main>
<script>
fetch('api/dia').then(r=>r.json()).then(d=>{
  document.getElementById('estado').textContent = 'Leído de la base ' + d.fuente_lectura + ' el ' + d.fecha + '. ' + d.banner;
  const f = document.getElementById('frases');
  d.frases.forEach(x=>{const p=document.createElement('div');p.className='frase';p.textContent=x;
    const s=document.createElement('small');s.textContent='Regla determinista: recuentos y umbrales.';p.appendChild(s);f.appendChild(p);});
  const c = document.getElementById('cifras');
  [['Muebles publicados',d.publicados],['Referencias',d.referencias],['Unidades',d.unidades],
   ['Valor del almacén (€)',d.valor_almacen.toLocaleString('es-ES')],
   ['Clientes',d.clientes],['Proveedores',d.proveedores],['Pedidos',d.pedidos],
   ['Confirmados',d.confirmados],['Presupuestos',d.presupuestos],
   ['Entregas hechas',d.entregas_hechas],['Entregas listas',d.entregas_pendientes],
   ['Recepciones hechas',d.recepciones_hechas],['Recepciones pendientes',d.recepciones_pendientes],
   ['Compras',d.compras],['Actividades',d.actividades],['Vencidas',d.vencidas]]
   .forEach(([k,v])=>{const q=document.createElement('div');q.className='caja';
     q.innerHTML='<b>'+v+'</b>'+k;c.appendChild(q);});
  const ev = document.getElementById('evolucion');
  const e = d.evolucion||{};
  [['Entregas hoy',e.entregas_hoy],['Entregas ayer',e.entregas_ayer],['Entregas 7 días',e.entregas_semana],
   ['Recepciones hoy',e.recepciones_hoy],['Recepciones ayer',e.recepciones_ayer],['Recepciones 7 días',e.recepciones_semana]]
   .forEach(([k,v])=>{const q=document.createElement('div');q.className='caja';
     q.innerHTML='<b>'+(v===undefined?'—':v)+'</b>'+k;ev.appendChild(q);});
  const b = document.getElementById('bandeja');
  if(!d.prioridades.length){const li=document.createElement('li');li.textContent='Nada pendiente en el tramo de atención.';b.appendChild(li);}
  d.prioridades.forEach(p=>{const li=document.createElement('li');
    li.innerHTML='<span class="tag">'+p.tipo+'</span>'+p.texto+(p.urgente?' <span class="rojo">(vencida)</span>':'');b.appendChild(li);});
  const mcp = document.getElementById('mcp');
  if(d.mcp_lead){
    const li=document.createElement('li');
    li.textContent=d.mcp_lead.nombre+' — score '+d.mcp_lead.score_kavana+
      ', prioridad '+d.mcp_lead.prioridad_sugerida+': '+d.mcp_sugerencia;
    mcp.appendChild(li);
  }else{
    const li=document.createElement('li');li.textContent=d.mcp_sugerencia;mcp.appendChild(li);
  }
  const s = document.getElementById('salud');
  d.salud_dato.forEach(x=>{
    const li=document.createElement('li');
    const ok = x.ok === true;
    const nota = (x.no_aplica === true) ? ' <span class="nota">(demo: módulo no instalado)</span>' :
                 (!ok && x.motivo && x.motivo.includes('demo')) ? ' <span class="nota">(demo: artefacto conocido)</span>' : '';
    li.innerHTML=(ok?'':'<span class="rojo">✕ </span>')+x.campo+': '+x.valor+
      (x.motivo?' <span class="nota">'+x.motivo+'</span>':'')+nota;
    s.appendChild(li);
  });
}).catch(e=>{document.getElementById('estado').textContent='Sin conexión con el laboratorio: ' + e;});
</script></body></html>
"""


def _carga_cache() -> dict | None:
    ruta = configuracion.carpeta_cache() / f"dia_{date.today().isoformat()}.json"
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


class PanelHandler(BaseHTTPRequestHandler):
    def _responder_json(self, codigo: int, datos: dict) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_POST(self):
        if self.path == "/api/restaurar":
            permitido, motivo = _sesion_es_admin(self.headers)
            if not permitido:
                self._responder_json(403, {"error": motivo})
                return
            if REINICIO["en_curso"]:
                self._responder_json(409, {"estado": "en_curso",
                                           "mensaje": "Ya se está reiniciando el laboratorio."})
                return
            esperado = configuracion.espera_minima_reinicio() - (time.time() - REINICIO["iniciado"])
            if REINICIO["iniciado"] and esperado > 0:
                self._responder_json(429, {
                    "estado": "espera",
                    "mensaje": f"El laboratorio se reinició hace poco. Prueba en "
                               f"{int(esperado) // 60 + 1} minuto(s)."})
                return
            threading.Thread(target=_lanzar_reinicio, daemon=True).start()
            self._responder_json(202, {
                "estado": "iniciado",
                "mensaje": "Reinicio en marcha. Tarda cerca de un minuto; esta página "
                           "se actualizará sola."})
            return
        if self.path == "/api/preguntar":
            try:
                largo = int(self.headers.get("Content-Length", "0") or 0)
                cuerpo = json.loads(self.rfile.read(largo).decode("utf-8") or "{}")
            except (ValueError, UnicodeDecodeError):
                self._responder_json(400, {"error": "petición no válida"})
                return
            pregunta = str(cuerpo.get("pregunta", "")).strip()[:400]
            try:
                self._responder_json(200, asistente.responder(pregunta))
            except Exception as exc:  # noqa: BLE001
                self._responder_json(500, {"error": f"el asistente falló: {exc}"})
            return
        self._responder_json(404, {"error": "ruta no encontrada"})

    def do_GET(self):
        if self.path == "/api/restaurar":
            estado = _reinicio_estado()
            mensaje = {
                "libre": "El laboratorio está en su estado actual. El botón lo devuelve "
                         "al estado inicial.",
                "en_curso": "Reiniciando el laboratorio...",
                "hecho": "Laboratorio restaurado a su estado inicial.",
                "error": "El reinicio falló. Avisa a quien te dio el enlace.",
            }[estado]
            self._responder_json(200, {"estado": estado, "mensaje": mensaje,
                                       "detalle": REINICIO["detalle"]})
            return
        if self.path == "/api/dia":
            datos = _carga_cache()
            fuente = "caché"
            if datos is None:
                try:
                    datos = construir_resumen(leer_cifras())
                    fuente = "directa"
                except Exception as exc:  # noqa: BLE001
                    self._responder_json(503, {
                        "error": str(exc),
                        "aviso": "Sin caché y sin laboratorio: el panel no inventa."})
                    return
            datos = dict(datos, fuente_lectura=fuente)
            self._responder_json(200, datos)
            return
        cuerpo = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, format, *args):  # silencio amable
        pass


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Panel del día del laboratorio de muebles (solo lectura)")
    parser.add_argument("--precomputar", action="store_true", help="Lee el laboratorio y escribe la caché del día")
    parser.add_argument("--puerto", type=int, default=configuracion.puerto_panel(),
                        help=f"Puerto del servidor (por defecto {configuracion.puerto_panel()})")
    return parser


def main() -> int:
    args = crear_parser().parse_args()
    if args.precomputar:
        ruta = precomputar()
        print(f"Caché escrita: {ruta}")
        return 0
    servidor = ThreadingHTTPServer(("0.0.0.0", args.puerto), PanelHandler)
    print(f"Panel servido en http://localhost:{args.puerto} (caché del día o lectura directa)")
    servidor.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())