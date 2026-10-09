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
import json
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import configuracion  # noqa: E402
import asistente  # noqa: E402

BANNER = "Laboratorio de demostración — Muebles del Hogar S.L. (base furniture_db)"
CATALOGO = ("pc.complete_name LIKE 'Muebles de Hogar%'")

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
    proceso = subprocess.run([sys.executable, str(script), "--restaurar"],
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
            f"{cifras['dias_presupuesto_viejo']} días sin respuesta: eso sí es dinero parado.")
    if cifras.get("actividades"):
        frases.append(
            f"He revisado {n(cifras['actividades'])} actividades asignadas: "
            f"{n(cifras['vencidas'])} vencidas, {n(cifras['hoy'])} de hoy, "
            f"{n(cifras['manana'])} de mañana y {n(cifras['proximas'])} próximas. "
            f"Lo que necesita decisión son las {n(cifras['vencidas'])} vencidas.")

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
                               int(evolucion.get("recepciones_semana", 0))))

    salud = cifras.get("salud_dato", [])
    faltan = [s["campo"] for s in salud if not s.get("ok") and not s.get("no_aplica")]
    ia = []
    if faltan:
        frases.append(
            "Salud del dato: no puedo afirmar nada de " + ", ".join(faltan) +
            ". Si falta el dato, me paro y digo por qué.")
    ia.append("Resumen redactado con reglas deterministas precomputadas: sin clave de "
              "modelo no hay redacción por IA, y así se declara en vez de aparentarlo.")
    return {**cifras, "frases": frases, "ia": ia, "salud_dato": salud}


# ---------------------------------------------------------------------------
# Lectura del laboratorio (solo lectura, por SQL del contenedor)
# ---------------------------------------------------------------------------

def _sql(consulta: str) -> list[list[str]]:
    res = subprocess.run(
        [configuracion.docker(), "exec", configuracion.contenedor_bd(),
         "psql", "-U", "odoo", "-d", configuracion.base_de_datos(), "-tAF", "|", "-c", consulta],
        capture_output=True, text=True, timeout=30,
    )
    if res.returncode != 0:
        raise RuntimeError(f"SQL falló: {res.stderr.strip()[:200]}")
    return [linea.split("|") for linea in res.stdout.splitlines() if linea.strip()]


def _numero(consulta: str, por_defecto: int = 0) -> int:
    try:
        filas = _sql(consulta)
    except Exception:  # noqa: BLE001  (una tabla que no existe no debe tumbar el panel)
        return por_defecto
    if not filas or not filas[0] or filas[0][0] == "":
        return por_defecto
    return int(float(filas[0][0]))


def _decimal(consulta: str, por_defecto: float = 0.0) -> float:
    try:
        filas = _sql(consulta)
    except Exception:  # noqa: BLE001
        return por_defecto
    if not filas or not filas[0] or filas[0][0] == "":
        return por_defecto
    return float(filas[0][0])


def leer_cifras() -> dict:
    """Cifras del panel, leídas del contenedor de PostgreSQL."""
    unidades = _numero(
        "SELECT round(sum(q.quantity)) FROM stock_quant q "
        "JOIN stock_location l ON l.id = q.location_id "
        "WHERE l.usage = 'internal' AND q.quantity > 0")
    traza_existencias = _numero(
        "SELECT round(sum(q.quantity)) FROM stock_quant q "
        "JOIN stock_location l ON l.id = q.location_id WHERE l.usage = 'internal'")
    traza_movimientos = _numero(
        "SELECT round(coalesce(sum(CASE WHEN ld.usage = 'internal' THEN m.quantity ELSE 0 END) "
        " - sum(CASE WHEN lo.usage = 'internal' THEN m.quantity ELSE 0 END), 0)) "
        "FROM stock_move m "
        "JOIN stock_location lo ON lo.id = m.location_id "
        "JOIN stock_location ld ON ld.id = m.location_dest_id WHERE m.state = 'done'")
    fuera_catalogo = _numero(
        "SELECT count(*) FROM sale_order_line sol WHERE sol.product_id NOT IN ("
        " SELECT pp.id FROM product_product pp"
        " JOIN product_template pt ON pt.id = pp.product_tmpl_id"
        " JOIN product_category pc ON pc.id = pt.categ_id WHERE " + CATALOGO + ")")

    dias = _numero(
        "SELECT coalesce(max(current_date - date_order::date), 0) FROM sale_order "
        "WHERE state IN ('draft','sent')")
    viejos = _numero(
        "SELECT count(*) FROM sale_order WHERE state IN ('draft','sent') "
        "AND (current_date - date_order::date) >= 7")

    cifras = {
        "fecha": date.today().isoformat(),
        "banner": BANNER,
        "productos": _numero("SELECT count(*) FROM product_template WHERE active"),
        "publicados": _numero("SELECT count(*) FROM product_template WHERE is_published"),
        "modelo": _numero("SELECT count(*) FROM furniture_product"),
        "clientes": _numero("SELECT count(*) FROM res_partner WHERE customer_rank > 0"),
        "proveedores": _numero("SELECT count(*) FROM res_partner WHERE supplier_rank > 0"),
        "pedidos": _numero("SELECT count(*) FROM sale_order"),
        "confirmados": _numero("SELECT count(*) FROM sale_order WHERE state = 'sale'"),
        "presupuestos": _numero("SELECT count(*) FROM sale_order WHERE state IN ('draft','sent')"),
        "cancelados": _numero("SELECT count(*) FROM sale_order WHERE state = 'cancel'"),
        "entregas_hechas": _numero(
            "SELECT count(*) FROM stock_picking sp JOIN stock_picking_type pt "
            "ON pt.id = sp.picking_type_id WHERE pt.code = 'outgoing' AND sp.state = 'done'"),
        "entregas_pendientes": _numero(
            "SELECT count(*) FROM stock_picking sp JOIN stock_picking_type pt "
            "ON pt.id = sp.picking_type_id WHERE pt.code = 'outgoing' AND sp.state NOT IN ('done','cancel')"),
        "recepciones_hechas": _numero(
            "SELECT count(*) FROM stock_picking sp JOIN stock_picking_type pt "
            "ON pt.id = sp.picking_type_id WHERE pt.code = 'incoming' AND sp.state = 'done'"),
        "recepciones_pendientes": _numero(
            "SELECT count(*) FROM stock_picking sp JOIN stock_picking_type pt "
            "ON pt.id = sp.picking_type_id WHERE pt.code = 'incoming' AND sp.state NOT IN ('done','cancel')"),
        "compras": _numero("SELECT count(*) FROM purchase_order"),
        "compras_pendientes": _numero(
            "SELECT count(DISTINCT pol.order_id) FROM purchase_order_line pol "
            "JOIN stock_move sm ON sm.purchase_line_id = pol.id "
            "WHERE sm.state NOT IN ('done','cancel')"),
        "asientos": _numero("SELECT count(*) FROM account_move"),
        "referencias": _numero(
            "SELECT count(*) FROM stock_quant q JOIN stock_location l ON l.id = q.location_id "
            "WHERE l.usage = 'internal' AND q.quantity > 0"),
        "unidades": unidades,
        "valor_almacen": _decimal(
            "SELECT round(sum(svl.value)::numeric, 2) FROM stock_valuation_layer svl"),
        "actividades": _numero("SELECT count(*) FROM mail_activity"),
        "vencidas": _numero("SELECT count(*) FROM mail_activity WHERE date_deadline < current_date"),
        "hoy": _numero("SELECT count(*) FROM mail_activity WHERE date_deadline = current_date"),
        "manana": _numero("SELECT count(*) FROM mail_activity WHERE date_deadline = current_date + 1"),
        "proximas": _numero("SELECT count(*) FROM mail_activity WHERE date_deadline > current_date + 1"),
        "presupuestos_viejos": viejos,
        "dias_presupuesto_viejo": dias if viejos else 0,
    }

    salud = [
        {"campo": "almacén respaldado por movimientos",
         "valor": f"{formato_numero(traza_existencias)} / {formato_numero(traza_movimientos)}",
         "ok": traza_existencias == traza_movimientos,
         "motivo": f"{formato_numero(abs(traza_existencias - traza_movimientos))} unidades sin movimiento"},
        {"campo": "pedidos sobre el catálogo",
         "valor": "todos" if fuera_catalogo == 0 else f"{fuera_catalogo} fuera",
         "ok": fuera_catalogo == 0,
         "motivo": f"{fuera_catalogo} líneas apuntan a productos que no son del catálogo"},
        {"campo": "valoración del almacén",
         "valor": f"{formato_numero(cifras['valor_almacen'])} €",
         "ok": cifras["valor_almacen"] > 0,
         "motivo": "sin apuntes de valoración"},
        {"campo": "tickets de soporte (helpdesk)",
         "valor": 0, "ok": False, "no_aplica": True, "motivo": "no existe en la edición Community"},
        {"campo": "tareas de proyecto",
         "valor": _numero("SELECT count(*) FROM project_task"),
         "ok": _numero("SELECT count(*) FROM project_task") > 0,
         "no_aplica": True, "motivo": "módulo sin usar"},
    ]
    cifras["salud_dato"] = salud

    prioridades = []
    for login, resumen, modelo, res_id, dias_act in _sql(
            "SELECT u.login, a.summary, a.res_model, a.res_id, (a.date_deadline - current_date) "
            "FROM mail_activity a JOIN res_users u ON u.id = a.user_id "
            "WHERE a.date_deadline <= current_date + 1 ORDER BY a.date_deadline LIMIT 4"):
        prioridades.append({
            "tipo": "actividad", "etiqueta": login.split("@")[0],
            "texto": f"{resumen} ({modelo} #{res_id})",
            "urgente": int(dias_act or 0) <= 0,
        })
    for nombre, cliente in _sql(
            "SELECT sp.name, coalesce(rp.name, so.name, '(sin cliente)') "
            "FROM stock_picking sp JOIN stock_picking_type pt ON pt.id = sp.picking_type_id "
            "LEFT JOIN res_partner rp ON rp.id = sp.partner_id "
            "LEFT JOIN sale_order so ON so.id = sp.sale_id "
            "WHERE pt.code = 'outgoing' AND sp.state NOT IN ('done','cancel') "
            "ORDER BY sp.scheduled_date LIMIT 3"):
        prioridades.append({"tipo": "entrega", "etiqueta": nombre,
                            "texto": f"Entrega preparada para {cliente}", "urgente": False})
    for nombre, proveedor in _sql(
            "SELECT sp.name, coalesce(rp.name, '(sin proveedor)') "
            "FROM stock_picking sp JOIN stock_picking_type pt ON pt.id = sp.picking_type_id "
            "LEFT JOIN res_partner rp ON rp.id = sp.partner_id "
            "WHERE pt.code = 'incoming' AND sp.state NOT IN ('done','cancel') "
            "ORDER BY sp.scheduled_date LIMIT 3"):
        prioridades.append({"tipo": "recepción", "etiqueta": nombre,
                            "texto": f"Recepción pendiente de {proveedor}", "urgente": False})
    cifras["prioridades"] = prioridades

    # ------------------------------------------------------------------
    # Comparación de periodos (patrón MIS, benchmark punto 2): el
    # movimiento de hoy frente al de ayer y al total de 7 días.
    # ------------------------------------------------------------------
    def hechas(code: str, desde: str, hasta: str) -> int:
        return _numero(
            "SELECT count(*) FROM stock_picking sp "
            "JOIN stock_picking_type pt ON pt.id = sp.picking_type_id "
            f"WHERE pt.code = '{code}' AND sp.state = 'done' "
            f"AND sp.date_done::date >= '{desde}' AND sp.date_done::date <= '{hasta}'")

    hoy = date.today()
    ayer = date.fromordinal(hoy.toordinal() - 1)
    hace_7 = date.fromordinal(hoy.toordinal() - 6)
    cifras["evolucion"] = {
        "entregas_hoy": hechas('outgoing', hoy.isoformat(), hoy.isoformat()),
        "entregas_ayer": hechas('outgoing', ayer.isoformat(), ayer.isoformat()),
        "entregas_semana": hechas('outgoing', hace_7.isoformat(), hoy.isoformat()),
        "recepciones_hoy": hechas('incoming', hoy.isoformat(), hoy.isoformat()),
        "recepciones_ayer": hechas('incoming', ayer.isoformat(), ayer.isoformat()),
        "recepciones_semana": hechas('incoming', hace_7.isoformat(), hoy.isoformat()),
    }
    return cifras


def precomputar() -> Path:
    """Lee el laboratorio y escribe la caché del día."""
    carpeta = configuracion.carpeta_cache()
    carpeta.mkdir(exist_ok=True)
    resumen = construir_resumen(leer_cifras())
    destino = carpeta / f"dia_{date.today().isoformat()}.json"
    destino.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


# ---------------------------------------------------------------------------
# Servidor (solo lo sirve; no escribe en el laboratorio)
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
footer{margin:20px 0;color:#9a8d80;font-size:12px}
</style></head><body>
<div class="banner">Laboratorio de demostración — Muebles del Hogar S.L. (base furniture_db)</div>
<main><h1>Panel del día</h1><div class="sub" id="estado">Cargando...</div>
<div id="frases"></div>
<h2>Cifras del día</h2><div class="cifras" id="cifras"></div>
<h2>Comparado con otros días</h2><div class="cifras" id="evolucion"></div>
<h2>Lo que pide atención</h2><ul id="bandeja"></ul>
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
    li.innerHTML='<span class="tag">'+p.tipo+'</span>'+p.texto+(p.urgente?' <span class="rojo">(vencida)</span>':'');
    b.appendChild(li);});
  const s = document.getElementById('salud');
  d.salud_dato.forEach(x=>{const li=document.createElement('li');
    li.innerHTML=(x.ok?'':'<span class="rojo">✕ </span>')+x.campo+': '+x.valor+(x.ok?'':' — '+x.motivo);s.appendChild(li);});
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
