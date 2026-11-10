#!/usr/bin/env bash
# Despliegue de ODOO_CRM v2 en el servidor de la demo (y vuelta atrás).
#
#   sudo scripts/despliegue/desplegar_v2.sh comprobar     # solo lectura: ¿se puede?
#   sudo scripts/despliegue/desplegar_v2.sh desplegar     # copia, PG 15 -> 17, v2, panel, instantánea
#   sudo scripts/despliegue/desplegar_v2.sh volver_atras  # vuelve a la v1 sobre PostgreSQL 15
#
# Qué hace «desplegar», en orden (para al primer fallo):
#   1. comprueba que se puede (lo mismo que «comprobar»);
#   2. para la limpieza automática y el panel, y deja la demo en su estado canónico;
#   3. copia de seguridad de TODAS las bases (pg_dump -Fc), de los roles, del
#      filestore y de la instantánea v1, en COPIAS/<fecha>;
#   4. pasa el repositorio a la v2 (fast-forward de main);
#   5. levanta PostgreSQL 17 en un volumen NUEVO (el de la 15 no se toca: es la
#      vuelta atrás) y restaura ahí las bases;
#   6. actualiza el módulo en cada base que lo tiene (migración 20.0.2.0.0);
#   7. arranca Odoo, crea el usuario de integración y su API key, cambia la
#      contraseña del usuario de visita;
#   8. hace la nueva instantánea canónica (la v1 queda guardada);
#   9. arranca el panel con la clave, prueba un ciclo de restauración y
#      reactiva la limpieza automática.
#
# Variables (por defecto, las del servidor de la demo):
REPO_DIR="${REPO_DIR:-/root/ODOO_CRM}"
REF_V2="${REF_V2:-origin/main}"
REF_V1="${REF_V1:-5ec6960ab157d3790f97986a3b74713a29bf0a5c}"
COPIAS_RAIZ="${COPIAS_RAIZ:-/root/copias/odoo_crm}"
SNAPSHOT="${MUEBLES_SNAPSHOT:-/root/.hermes/profiles/hermes2/trabajo/muebles-demo/snapshot_muebles_demo_canonico.sql.gz}"
BASE="${MUEBLES_DB:-furniture_db}"
CONT_BD="${MUEBLES_DB_CONTAINER:-furniture_db}"
CONT_ODOO="${MUEBLES_ODOO_CONTAINER:-furniture_odoo}"
PUERTO_ODOO="${MUEBLES_ODOO_PORT:-8070}"
PUERTO_PANEL="${MUEBLES_PANEL_PORT:-8081}"
SIN_SYSTEMD="${SIN_SYSTEMD:-0}"          # 1 en el ensayo del CI
# Fichero de entorno que ya leen muebles-panel.service y muebles-restore.service
PANEL_ENV="${PANEL_ENV:-/etc/muebles/panel.env}"
PANEL_DROPIN="/etc/systemd/system/muebles-panel.service.d/odoo-api.conf"
PY="${PY:-python3}"
DISCO="${DISCO:-/root}"                  # carpeta cuyo disco recibe las copias

set -euo pipefail
ESTADO="$COPIAS_RAIZ/ultimo_despliegue"   # apunta a la carpeta de copias del último despliegue

# El script cambia de versión su propio repositorio (git merge / checkout) y
# bash lee los scripts a medida que avanza: se ejecuta siempre desde una copia.
if [ -z "${DESPLIEGUE_DESDE_COPIA:-}" ]; then
  copia="$(mktemp /tmp/desplegar_v2.XXXXXX)"
  cp "$0" "$copia"
  DESPLIEGUE_DESDE_COPIA=1 exec bash "$copia" "$@"
fi

paso() { printf '\n==> %s\n' "$*"; }
falla() { printf '\nPARADO: %s\n' "$*" >&2; exit 1; }
compose() { docker compose -f "$REPO_DIR/docker-compose.yml" "$@"; }
psql_bd() { docker exec "$CONT_BD" psql -v ON_ERROR_STOP=1 -U odoo "$@" < /dev/null; }
version_pg() { docker exec "$CONT_BD" postgres --version | grep -oE '[0-9]+' | head -1; }

systemd() {
  if [ "$SIN_SYSTEMD" = "1" ]; then echo "  (sin systemd) systemctl $*"; return 0; fi
  systemctl "$@"
}

esperar_odoo() {
  for _ in $(seq 1 200); do
    if curl -sf -o /dev/null "http://127.0.0.1:$PUERTO_ODOO/web/login"; then return 0; fi
    sleep 3
  done
  falla "Odoo no responde en el puerto $PUERTO_ODOO tras 10 minutos (docker logs $CONT_ODOO)"
}

esperar_pg() {
  for _ in $(seq 1 60); do
    if docker exec "$CONT_BD" pg_isready -U odoo >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  falla "PostgreSQL no arranca (docker logs $CONT_BD)"
}

bases_con_modulo() {
  # Bases de datos (no plantillas del sistema) que tienen ODOO_CRM instalado.
  local base
  for base in $(psql_bd -d postgres -tAc "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1"); do
    if psql_bd -d "$base" -tAc "SELECT 1 FROM ir_module_module WHERE name = 'ODOO_CRM' AND state = 'installed'" 2>/dev/null | grep -q 1; then
      echo "$base"
    fi
  done
}

comprobar() {
  local bloqueos=0
  paso "Comprobaciones (solo lectura)"
  [ -d "$REPO_DIR/.git" ] || falla "no hay repositorio en $REPO_DIR"
  git -C "$REPO_DIR" fetch -q origin
  echo "  repo: $(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD) @ $(git -C "$REPO_DIR" rev-parse --short HEAD)"
  echo "  v2 a desplegar: $(git -C "$REPO_DIR" rev-parse --short "$REF_V2")"
  if ! git -C "$REPO_DIR" merge-base --is-ancestor HEAD "$REF_V2"; then
    echo "  BLOQUEO: HEAD no es antecesor de $REF_V2 (no sería un fast-forward)"; bloqueos=1
  fi
  if [ -n "$(git -C "$REPO_DIR" status --porcelain --untracked-files=no)" ]; then
    echo "  BLOQUEO: hay cambios sin confirmar en ficheros del repositorio:"
    git -C "$REPO_DIR" status --short --untracked-files=no | sed 's/^/    /'; bloqueos=1
  fi
  local pg; pg="$(version_pg)"
  echo "  PostgreSQL de la demo: $pg"
  if [ "$pg" != "15" ]; then
    echo "  BLOQUEO: se esperaba PostgreSQL 15 (¿ya desplegado?)"; bloqueos=1
  fi
  local bases; bases="$(bases_con_modulo | tr '\n' ' ')"
  echo "  bases con ODOO_CRM: ${bases:-ninguna}"
  [ -n "$bases" ] || { echo "  BLOQUEO: ninguna base tiene ODOO_CRM instalado"; bloqueos=1; }
  for base in $bases; do
    echo "    $base: versión $(psql_bd -d "$base" -tAc "SELECT latest_version FROM ir_module_module WHERE name = 'ODOO_CRM'")"
  done
  if [ -d "$REPO_DIR/addons" ] && [ -n "$(ls -A "$REPO_DIR/addons" 2>/dev/null)" ]; then
    echo "  aviso: $REPO_DIR/addons tiene contenido; la v2 lo sigue montando igual:"
    ls -A "$REPO_DIR/addons" | sed 's/^/    /'
  fi
  # El compose v2 deja de publicar PostgreSQL en 127.0.0.1:5434. Si algo del
  # servidor lo usa (copias, scripts), se rompería sin avisar.
  local usos
  usos="$( { crontab -l 2>/dev/null || true; cat /etc/crontab /etc/cron.d/* 2>/dev/null || true;
             grep -rIl --exclude-dir=.git --exclude-dir=node_modules 5434 /etc/systemd/system /root/*.sh /root/scripts /root/bin 2>/dev/null || true; } | grep -n 5434 || true)"
  if [ -n "$usos" ]; then
    echo "  BLOQUEO: algo del servidor usa el puerto 5434 de PostgreSQL:"; echo "$usos" | sed 's/^/    /'; bloqueos=1
  fi
  [ -f "$SNAPSHOT" ] || { echo "  BLOQUEO: no existe la instantánea $SNAPSHOT"; bloqueos=1; }
  local libre_kb tam_kb
  libre_kb="$(df -Pk "$DISCO" | awk 'NR==2 {print $4}')"
  tam_kb="$(psql_bd -d postgres -tAc "SELECT (sum(pg_database_size(datname)) / 1024)::bigint FROM pg_database")"
  echo "  bases: $((tam_kb / 1024)) MB · libre: $((libre_kb / 1024)) MB"
  if [ "$libre_kb" -lt $((tam_kb * 4)) ]; then
    echo "  BLOQUEO: hace falta al menos 4 veces el tamaño de las bases libre en disco"; bloqueos=1
  fi
  [ "$bloqueos" = "0" ] || falla "hay bloqueos: no se toca nada"
  echo "  se puede desplegar"
}

desplegar() {
  comprobar
  local fecha copias
  fecha="$(date +%Y%m%d-%H%M%S)"
  copias="$COPIAS_RAIZ/$fecha"
  mkdir -p "$copias"; chmod 700 "$COPIAS_RAIZ" "$copias"
  echo "$copias" > "$ESTADO"
  git -C "$REPO_DIR" rev-parse HEAD > "$copias/head_anterior"

  paso "Parar la limpieza automática y el panel; dejar la demo en su estado canónico"
  systemd stop muebles-restore.timer || true
  if [ "$SIN_SYSTEMD" != "1" ]; then
    # El temporizador salta a :00 y :30: si hay una restauración en marcha, se espera.
    # Es un servicio oneshot: mientras corre está en "activating", no en
    # "active", así que se mira el estado exacto (fallo visto el 07-11).
    # También la del botón del panel (muebles-restore-ahora), si la hay.
    for unidad in muebles-restore.service muebles-restore-ahora.service; do
      while [ "$(systemctl show -p ActiveState --value "$unidad")" != "inactive" ] \
            && [ "$(systemctl show -p ActiveState --value "$unidad")" != "failed" ]; do
        echo "  restauración en curso ($unidad): esperando"; sleep 10
      done
    done
  fi
  systemd stop muebles-panel.service || true
  MUEBLES_SNAPSHOT="$SNAPSHOT" "$PY" "$REPO_DIR/panel/demo_restaurar_muebles.py" --restaurar --sin-refrescar-panel

  paso "Copia de seguridad en $copias"
  compose stop odoo
  local bases; bases="$(bases_con_modulo)"
  echo "$bases" > "$copias/bases_con_modulo"
  for base in $(psql_bd -d postgres -tAc "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1"); do
    docker exec "$CONT_BD" pg_dump -U odoo -Fc -d "$base" > "$copias/$base.dump"
    docker exec -i "$CONT_BD" pg_restore -l < "$copias/$base.dump" > /dev/null
    echo "$base" >> "$copias/bases"
    echo "  $base: $(du -h "$copias/$base.dump" | cut -f1)"
  done
  docker exec "$CONT_BD" pg_dumpall -U odoo --globals-only > "$copias/roles.sql"
  docker run --rm --user root --volumes-from "$CONT_ODOO" -v "$copias:/copia" --entrypoint tar \
    odoo:20 czf /copia/filestore.tgz -C /var/lib/odoo .
  cp "$SNAPSHOT" "$copias/instantanea_v1.sql.gz"
  if [ -f "$PANEL_ENV" ]; then cp -p "$PANEL_ENV" "$copias/panel.env.v1"; fi
  echo "  copias verificadas (pg_restore -l) y filestore guardado"

  paso "Repositorio a la v2 ($REF_V2)"
  git -C "$REPO_DIR" merge --ff-only "$REF_V2"
  echo "  ahora en $(git -C "$REPO_DIR" rev-parse --short HEAD)"

  paso "PostgreSQL 17 en un volumen nuevo (el de la 15 queda intacto)"
  compose up -d db
  esperar_pg
  [ "$(version_pg)" = "17" ] || falla "el contenedor de la base no es PostgreSQL 17"
  while read -r base; do
    [ -n "$base" ] || continue
    psql_bd -d postgres -c "CREATE DATABASE \"$base\" OWNER odoo TEMPLATE template0" > /dev/null
    docker exec -i "$CONT_BD" pg_restore -U odoo -d "$base" --no-owner --role=odoo --exit-on-error < "$copias/$base.dump"
    echo "  $base restaurada"
  done < "$copias/bases"

  paso "Actualizar ODOO_CRM en cada base (migración 20.0.2.0.0)"
  while read -r base; do
    [ -n "$base" ] || continue
    compose run --rm --no-deps -T odoo odoo -d "$base" -u ODOO_CRM --stop-after-init --no-http \
      < /dev/null > "$copias/actualizar_$base.log" 2>&1 || { tail -40 "$copias/actualizar_$base.log"; falla "la actualización de $base falló"; }
    bash "$REPO_DIR/ci/comprobar_log_odoo.sh" "$copias/actualizar_$base.log" || falla "errores en el log de $base"
    grep "ODOO_CRM 2.0" "$copias/actualizar_$base.log" | sed 's/^.*ODOO_CRM 2.0: /  '"$base"': /' || true
    psql_bd -d "$base" -c "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%'" > /dev/null
  done < "$copias/bases_con_modulo"

  paso "Arrancar Odoo"
  compose up -d odoo
  esperar_odoo

  paso "Usuario de integración del panel y contraseña de visita"
  local salida clave
  salida="$(compose exec -T odoo odoo shell -d "$BASE" --no-http < "$REPO_DIR/scripts/despliegue/usuario_integracion.py" 2>&1)"
  clave="$(echo "$salida" | sed -n 's/^API_KEY=//p' | tail -1)"
  [ -n "$clave" ] || { echo "$salida" | tail -20; falla "no se generó la API key"; }
  echo "$salida" | grep INTEGRACION_OK | sed 's/^/  /'
  mkdir -p "$(dirname "$PANEL_ENV")"
  umask 077
  # Se conserva lo que hubiera salvo las variables de la v1 (usuario y
  # contraseña JSON-RPC, que la v2 ya no usa) y las que se escriben ahora.
  { grep -vE '^(MUEBLES_JSONRPC_[A-Z]+|MUEBLES_ODOO_API_KEY|MUEBLES_ODOO_URL|MUEBLES_DB)=' "$PANEL_ENV" 2>/dev/null || true
    printf 'MUEBLES_ODOO_API_KEY=%s\nMUEBLES_ODOO_URL=http://127.0.0.1:%s\nMUEBLES_DB=%s\n' "$clave" "$PUERTO_ODOO" "$BASE"
  } > "$PANEL_ENV.nuevo"
  mv "$PANEL_ENV.nuevo" "$PANEL_ENV"
  echo "  clave guardada en $PANEL_ENV (permisos 600)"
  if [ "$SIN_SYSTEMD" != "1" ] && ! systemctl cat muebles-panel.service | grep -q "EnvironmentFile=-\?$PANEL_ENV"; then
    mkdir -p "$(dirname "$PANEL_DROPIN")"
    printf '[Service]\nEnvironmentFile=%s\n' "$PANEL_ENV" > "$PANEL_DROPIN"
    systemctl daemon-reload
  fi
  while read -r base; do
    [ -n "$base" ] || continue
    salida="$(compose exec -T odoo odoo shell -d "$base" --no-http < "$REPO_DIR/scripts/despliegue/rotar_visita.py" 2>&1)"
    if echo "$salida" | grep -q '^VISITA_PASSWORD='; then
      echo "$base: $(echo "$salida" | sed -n 's/^VISITA_PASSWORD=//p')" >> "$COPIAS_RAIZ/visita_password.txt"
      echo "  $base: contraseña de visita cambiada (guardada en $COPIAS_RAIZ/visita_password.txt)"
    fi
  done < "$copias/bases_con_modulo"
  umask 022

  paso "Nueva instantánea canónica (la v1 queda en $copias)"
  docker exec "$CONT_BD" pg_dump -U odoo -d "$BASE" | gzip > "$SNAPSHOT.nueva"
  gzip -t "$SNAPSHOT.nueva"
  mv "$SNAPSHOT.nueva" "$SNAPSHOT"
  echo "  $(du -h "$SNAPSHOT" | cut -f1) en $SNAPSHOT"

  paso "Panel y ciclo de restauración"
  systemd start muebles-panel.service
  MUEBLES_SNAPSHOT="$SNAPSHOT" "$PY" "$REPO_DIR/panel/demo_restaurar_muebles.py" --restaurar --sin-refrescar-panel
  if [ "$SIN_SYSTEMD" != "1" ]; then
    systemctl restart muebles-panel.service
    for _ in $(seq 1 30); do curl -sf -o /dev/null "http://127.0.0.1:$PUERTO_PANEL/api/dia" && break; sleep 2; done
    local dia; dia="$(curl -sf "http://127.0.0.1:$PUERTO_PANEL/api/dia" || true)"
    case "$dia" in
      *fichas_mobiliario*) ;;
      *) falla "el panel no responde con las cifras de la v2 (journalctl -u muebles-panel)" ;;
    esac
    echo "  panel leyendo por la API"
    MUEBLES_SNAPSHOT="$SNAPSHOT" "$PY" "$REPO_DIR/panel/demo_restaurar_muebles.py" --verificar
  fi
  systemd start muebles-restore.timer

  paso "HECHO"
  echo "  v2 en $(git -C "$REPO_DIR" rev-parse --short HEAD) · PostgreSQL $(version_pg)"
  echo "  copias y logs: $copias"
  echo "  la API key del panel caduca en 85 días: rotarla con"
  echo "    docker compose exec -T odoo odoo shell -d $BASE --no-http < scripts/despliegue/usuario_integracion.py"
}

volver_atras() {
  [ -f "$ESTADO" ] || falla "no hay ningún despliegue registrado en $ESTADO"
  local copias; copias="$(cat "$ESTADO")"
  paso "Volver a la v1 con las copias de $copias"
  systemd stop muebles-restore.timer || true
  systemd stop muebles-panel.service || true
  compose down
  git -C "$REPO_DIR" checkout -q "$(cat "$copias/head_anterior")"
  echo "  repo en $(git -C "$REPO_DIR" rev-parse --short HEAD) (detached; main sigue en la v2)"
  cp "$copias/instantanea_v1.sql.gz" "$SNAPSHOT"
  if [ -f "$copias/panel.env.v1" ]; then cp -p "$copias/panel.env.v1" "$PANEL_ENV"; fi
  if [ "$SIN_SYSTEMD" != "1" ]; then
    rm -f "$PANEL_DROPIN"; systemctl daemon-reload
  fi
  compose up -d
  esperar_pg
  [ "$(version_pg)" = "15" ] || falla "tras volver atrás la base no es PostgreSQL 15"
  esperar_odoo
  systemd start muebles-panel.service
  systemd start muebles-restore.timer
  paso "HECHO: v1 sobre PostgreSQL 15 (volumen original). Los datos de la v2 siguen en el volumen nuevo."
}

case "${1:-}" in
  comprobar) comprobar ;;
  desplegar) desplegar ;;
  volver_atras) volver_atras ;;
  *) echo "uso: $0 comprobar|desplegar|volver_atras" >&2; exit 2 ;;
esac
