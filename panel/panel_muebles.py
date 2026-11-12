#!/usr/bin/env python3
"""
Panel del día del laboratorio de muebles (Muebles del Hogar S.L.).

Para qué: dar a quien visita la demo una pantalla que resuma, en lenguaje de
negocio, cómo está la empresa hoy y qué pide atención, sin obligarle a entender
el ERP por dentro.

Principios de diseño (los mismos que el panel de aromas):
  - Solo lectura. El panel no escribe nada en el laboratorio; lee por la API
    externa de Odoo (JSON-2) con un usuario de integración que solo tiene el
    grupo «Panel del día: solo lectura» (ver panel/odoo_client.py). Nada de SQL:
    permisos, reglas y campos calculados del ORM se respetan.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import configuracion  # noqa: E402
import asistente  # noqa: E402
import odoo_client as fuente  # noqa: E402

BANNER = "Laboratorio de demostración — Muebles del Hogar S.L. (base furniture_db)"

# ---------------------------------------------------------------------------
# Módulos puros del repositorio (sin Odoo): la capa de sugerencias es una
# función determinista que se reutiliza tal cual desde el panel.
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
# Reinicio del laboratorio: el visitante entra como usuario interno con muchos
# permisos de datos y puede romper lo que quiera; el botón lo devuelve al estado inicial. Se exige la
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


def _orden_reinicio() -> list[str]:
    """Qué se ejecuta para restaurar.

    En el servidor el panel no es root: arranca la unidad privilegiada con sudo
    (regla estrecha, sin argumentos libres) y espera a que termine, porque
    «systemctl start» de una unidad oneshot no vuelve hasta que acaba. En local
    lanza el script directamente.
    """
    unidad = configuracion.unidad_restauracion()
    if unidad:
        return ["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "start", unidad]
    script = Path(__file__).resolve().parent / "demo_restaurar_muebles.py"
    return [sys.executable, str(script), "--restaurar", "--sin-refrescar-panel"]


def _lanzar_reinicio() -> None:
    """Ejecuta el motor de restauración en segundo plano (no bloquea el panel)."""
    with _CANDADO:
        REINICIO.update(en_curso=True, iniciado=time.time(), resultado=None,
                        detalle="Reiniciando el laboratorio (parar, recargar y arrancar).")
    try:
        proceso = subprocess.run(_orden_reinicio(), capture_output=True, text=True)
        codigo, salida = proceso.returncode, (proceso.stdout or proceso.stderr or "")
    except OSError as exc:  # sudo o systemctl no disponibles
        codigo, salida = 1, f"no se pudo lanzar la restauración: {exc}"
    with _CANDADO:
        REINICIO.update(en_curso=False,
                        resultado="hecho" if codigo == 0 else "error",
                        detalle=salida.strip()[-400:])
    if codigo == 0:  # la caché describe datos que ya no existen
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
# CRM: el score lo calcula el módulo dentro de Odoo; el panel solo lo lee
# ---------------------------------------------------------------------------
def oportunidad_crm() -> dict | None:
    """La oportunidad con mejor score y la acción que sugiere la capa de sugerencias.

    Hasta la v1 el panel recalculaba aquí el score con SQL y su propia regla de
    "contacto reciente", distinta de la del módulo. Ahora hay una sola fuente:
    los campos calculados x_score_kavana y x_prioridad_sugerida de crm.lead.
    Sin IA y sin azar: la misma entrada da la misma salida.
    """
    mejor = fuente.mejor_oportunidad()
    if mejor is None:
        return None
    sugerencias = _modulo_puro("_kavana_mcp", "mcp.py")
    mejor["mcp_sugerencia"] = sugerencias.MCPService.sugerir_accion(mejor)
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
    """Cifras del panel, leídas por la API de Odoo con el usuario de integración."""
    try:
        traza = fuente.traza_existencias_movimientos()
        existencias = traza["unidades"]
        unidades_trazadas = traza["unidades_trazadas"]
        fuera_catalogo = fuente.lineas_fuera_catalogo()
        dias_max = fuente.actividad_dias_max_presupuesto()
        viejos = fuente.presupuestos_viejos()
        oportunidad = oportunidad_crm()

        cifras = {
            "fecha": date.today().isoformat(),
            "banner": BANNER,
            "productos": fuente.productos_activos(),
            "publicados": fuente.productos_publicados(),
            "fichas_mobiliario": fuente.productos_con_ficha(),
            "clientes": fuente.clientes(),
            "proveedores": fuente.proveedores(),
            "pedidos": fuente.pedidos_totales(),
            "confirmados": fuente.pedidos_confirmados(),
            "presupuestos": fuente.pedidos_presupuesto(),
            "cancelados": fuente.pedidos_cancelados(),
            "entregas_hechas": fuente.entregas_hechas(),
            "entregas_pendientes": fuente.entregas_pendientes(),
            "recepciones_hechas": fuente.recepciones_hechas(),
            "recepciones_pendientes": fuente.recepciones_pendientes(),
            "compras": fuente.compras_totales(),
            "compras_pendientes": fuente.compras_pendientes(),
            "asientos": fuente.asientos_contables(),
            "referencias": fuente.referencias_con_stock(),
            "unidades": fuente.existencias_catalogo(),
            "valor_almacen": fuente.valor_almacen(),
            "actividades": fuente.actividades_totales(),
            "vencidas": fuente.actividades_vencidas(),
            "hoy": fuente.actividades_hoy(),
            "manana": fuente.actividades_manana(),
            "proximas": fuente.actividades_proximas(),
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
        prioridades.extend(fuente.prioridades_actividades())
        prioridades.extend(fuente.prioridades_entregas())
        prioridades.extend(fuente.prioridades_recepciones())
        cifras["prioridades"] = prioridades

        # Evolución (patrón MIS, benchmark punto 2)
        evolucion = {}
        evolucion.update(fuente.evolutivo_entregas())
        evolucion.update(fuente.evolutivo_recepciones())
        cifras["evolucion"] = evolucion

        return cifras

    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Lectura por la API de Odoo falló: {exc}") from exc


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
</style>
<script defer src="https://stats.kavanasystems.com/a.js" data-website-id="b383f20b-3b25-44e4-ae8d-582023687322" data-exclude-search="false"></script>
</head><body>
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
// Todo lo que viene de Odoo se pinta como texto (textContent), nunca como HTML.
function span(clase,texto){const e=document.createElement('span');e.className=clase;e.textContent=texto;return e;}
function caja(k,v){const q=document.createElement('div');q.className='caja';
  const b=document.createElement('b');b.textContent=String(v);
  q.appendChild(b);q.appendChild(document.createTextNode(k));return q;}
fetch('api/dia').then(r=>r.json()).then(d=>{
  document.getElementById('estado').textContent = 'Leído por la API de Odoo (' + d.fuente_lectura + ')' + ' el ' + d.fecha + '. ' + d.banner;
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
   .forEach(([k,v])=>c.appendChild(caja(k,v)));
  const ev = document.getElementById('evolucion');
  const e = d.evolucion||{};
  [['Entregas hoy',e.entregas_hoy],['Entregas ayer',e.entregas_ayer],['Entregas 7 días',e.entregas_semana],
   ['Recepciones hoy',e.recepciones_hoy],['Recepciones ayer',e.recepciones_ayer],['Recepciones 7 días',e.recepciones_semana]]
   .forEach(([k,v])=>ev.appendChild(caja(k,v===undefined?'—':v)));
  const b = document.getElementById('bandeja');
  if(!d.prioridades.length){const li=document.createElement('li');li.textContent='Nada pendiente en el tramo de atención.';b.appendChild(li);}
  d.prioridades.forEach(p=>{const li=document.createElement('li');
    li.appendChild(span('tag',p.tipo));
    li.appendChild(document.createTextNode(String(p.texto)));
    if(p.urgente){li.appendChild(document.createTextNode(' '));li.appendChild(span('rojo','(vencida)'));}
    b.appendChild(li);});
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
    const nota = (x.no_aplica === true) ? '(demo: módulo no instalado)' :
                 (!ok && x.motivo && x.motivo.includes('demo')) ? '(demo: artefacto conocido)' : '';
    if(!ok){li.appendChild(span('rojo','✕ '));}
    li.appendChild(document.createTextNode(x.campo+': '+x.valor));
    if(x.motivo){li.appendChild(document.createTextNode(' '));li.appendChild(span('nota',String(x.motivo)));}
    if(nota){li.appendChild(document.createTextNode(' '));li.appendChild(span('nota',nota));}
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
    def _ip_cliente(self) -> str:
        """IP del visitante. Detrás del proxy local se usa la última de X-Forwarded-For."""
        directa = self.client_address[0]
        if directa in ("127.0.0.1", "::1"):
            reenviada = self.headers.get("X-Forwarded-For", "")
            if reenviada:
                return reenviada.split(",")[-1].strip() or directa
        return directa

    def _responder_json(self, codigo: int, datos: dict) -> None:
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_POST(self):
        if self.path == "/api/restaurar":
            # Defensa CSRF: un formulario de otra web no puede añadir esta cabecera.
            if self.headers.get("X-Kavana-Restaurar") != "1":
                self._responder_json(403, {"error": "falta la cabecera de confirmación"})
                return
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
                if largo < 0 or largo > asistente.MAX_CUERPO:
                    self._responder_json(413, {"error": "petición demasiado grande"})
                    return
                cuerpo = json.loads(self.rfile.read(largo).decode("utf-8") or "{}")
                if not isinstance(cuerpo, dict):
                    raise ValueError("el cuerpo no es un objeto")
            except (ValueError, UnicodeDecodeError):
                self._responder_json(400, {"error": "petición no válida"})
                return
            pregunta = str(cuerpo.get("pregunta", "")).strip()[:400]
            permitido, aviso = asistente.LIMITADOR.pedir(self._ip_cliente())
            if not permitido:
                self._responder_json(429, {"error": aviso})
                return
            try:
                self._responder_json(200, asistente.responder(pregunta))
            except Exception:  # noqa: BLE001
                self._responder_json(500, {"error": "el asistente falló"})
            finally:
                asistente.LIMITADOR.soltar()
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
            origen = "caché"
            if datos is None:
                try:
                    datos = construir_resumen(leer_cifras())
                    origen = "lectura en vivo"
                except Exception as exc:  # noqa: BLE001
                    self._responder_json(503, {
                        "error": str(exc),
                        "aviso": "Sin caché y sin laboratorio: el panel no inventa."})
                    return
            datos = dict(datos, fuente_lectura=origen)
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
    host = configuracion.panel_host()
    servidor = ThreadingHTTPServer((host, args.puerto), PanelHandler)
    print(f"Panel servido en http://{host}:{args.puerto} (caché del día o lectura por la API)")
    servidor.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())