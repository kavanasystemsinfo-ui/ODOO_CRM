"""El panel del día contra un Odoo 20 real, con el usuario de integración.

Lee las cifras con panel_muebles.leer_cifras() (solo API JSON-2, ningún SQL)
y las compara con lo que cuenta el ORM como administrador. Después intenta
escribir con la misma API key: Odoo tiene que negarse.

    MUEBLES_ODOO_URL, MUEBLES_DB, MUEBLES_ODOO_API_KEY, ESPERADO=<json>
    python ci/probar_panel_api.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "panel"))

import configuracion  # noqa: E402
import odoo_client  # noqa: E402
import panel_muebles  # noqa: E402

esperado = json.loads(os.environ["ESPERADO"])
cifras = panel_muebles.leer_cifras()
resumen = panel_muebles.construir_resumen(cifras)

errores = []
for clave in ("productos", "publicados", "fichas_mobiliario", "clientes", "pedidos",
              "confirmados", "presupuestos", "entregas_pendientes", "unidades",
              "referencias", "valor_almacen"):
    if cifras[clave] != esperado[clave]:
        errores.append(f"{clave}: panel {cifras[clave]!r} / ORM {esperado[clave]!r}")

lead = cifras["mcp_lead"]
if not lead or lead["id"] != esperado["lead_id"]:
    errores.append(f"oportunidad destacada inesperada: {lead!r}")
elif lead["score_kavana"] != esperado["lead_score"]:
    errores.append(f"score: panel {lead['score_kavana']} / módulo {esperado['lead_score']}")
elif not lead["senales"]["contacto_reciente"]:
    errores.append("el mensaje al cliente debería contar como contacto reciente")
if not resumen["frases"]:
    errores.append("el resumen no tiene frases")

api = odoo_client.OdooJson2(configuracion.odoo_url(), configuracion.odoo_base(),
                            configuracion.odoo_api_key())
try:
    api("crm.lead", "write", ids=[esperado["lead_id"]], vals={"name": "escrito por el panel"})
    errores.append("el usuario de integración pudo ESCRIBIR en crm.lead")
except odoo_client.OdooClientError as exc:
    print("escritura rechazada, como se esperaba:", exc)
    if "HTTP 403" not in str(exc):
        errores.append(f"se esperaba HTTP 403 al escribir y llegó: {exc}")

print(json.dumps({k: cifras[k] for k in esperado if k in cifras}, ensure_ascii=False))
print("\n".join(resumen["frases"]))
if errores:
    print("PANEL_API_FALLIDO")
    print("\n".join(" - " + e for e in errores))
    sys.exit(1)
print("PANEL_API_OK")
