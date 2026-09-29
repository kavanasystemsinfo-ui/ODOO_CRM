#!/bin/bash
# Limpieza automática del laboratorio de muebles (Fase 1, 2026-09-29).
#
# Para qué: la demo la puede tocar cualquier visitante y ya no hay botón de
# reinicio en sus manos. Este script la devuelve a su estado inicial SOLO si
# alguien la ha tocado de verdad, así que un laboratorio intacto no se reinicia
# ni molesta a nadie.
#
# Cómo: primero comprueba los 14 recuentos del estado inicial (solo lectura). Si
# cuadran, no hace nada. Si no cuadran, restaura desde la instantánea canónica.
#
# Se ejecuta cada media hora desde cron (root).

set -uo pipefail

CARPETA="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-/usr/bin/python3}"
LOG="${LOG:-/var/log/muebles-limpieza.log}"
VERIFICACION="$(mktemp)"

if "$PY" "$CARPETA/demo_restaurar_muebles.py" --verificar >"$VERIFICACION" 2>&1; then
  echo "$(date -Is) intacto: no se toca" >>"$LOG"
  rm -f "$VERIFICACION"
  exit 0
fi

echo "$(date -Is) descuadrado (alguien lo ha tocado): restaurando" >>"$LOG"
sed 's/^/    /' "$VERIFICACION" >>"$LOG"
rm -f "$VERIFICACION"

if "$PY" "$CARPETA/demo_restaurar_muebles.py" --restaurar >>"$LOG" 2>&1; then
  echo "$(date -Is) restaurado al estado inicial" >>"$LOG"
else
  echo "$(date -Is) ⚠️ la restauración falló, revisar" >>"$LOG"
  exit 1
fi
