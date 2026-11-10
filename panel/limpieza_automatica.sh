#!/bin/bash
# Limpieza automática del laboratorio de muebles.
#
# Para qué: la demo la puede tocar cualquier visitante. Este script la devuelve
# a su estado inicial SOLO si alguien la ha tocado de verdad, así que un
# laboratorio intacto no se reinicia ni se interrumpe a quien la esté viendo.
#
# Cómo: primero comprueba los recuentos del estado inicial (solo lectura). Si
# cuadran, no hace nada. Si no cuadran, restaura desde la instantánea canónica.
#
# Lo ejecuta muebles-restore.service cada media hora (muebles-restore.timer).
# Bajo systemd escribe en el journal; con LOG=/ruta escribe en ese fichero.

set -uo pipefail

CARPETA="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-/usr/bin/python3}"
LOG="${LOG:-}"

registrar() {
  if [ -n "$LOG" ]; then cat >>"$LOG"; else cat; fi
}

VERIFICACION="$(mktemp)"
trap 'rm -f "$VERIFICACION"' EXIT

if "$PY" "$CARPETA/demo_restaurar_muebles.py" --verificar >"$VERIFICACION" 2>&1; then
  echo "$(date -Is) intacto: no se toca" | registrar
  exit 0
fi

echo "$(date -Is) descuadrado (alguien lo ha tocado): restaurando" | registrar
sed 's/^/    /' "$VERIFICACION" | registrar

if "$PY" "$CARPETA/demo_restaurar_muebles.py" --restaurar 2>&1 | registrar; then
  echo "$(date -Is) restaurado al estado inicial" | registrar
else
  echo "$(date -Is) la restauración falló, revisar" | registrar
  exit 1
fi
