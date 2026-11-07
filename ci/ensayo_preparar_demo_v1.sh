#!/usr/bin/env bash
# Monta en el runner del CI una copia de la demo tal como está hoy en el
# servidor: el repositorio en /root/ODOO_CRM en la v1, su docker-compose
# (Odoo 20 + PostgreSQL 15, volumen furniture_db_data), dos bases con el
# módulo v1 (furniture_db y muebles_plantilla) y la instantánea canónica.
#
# Odoo 20 no puede CREAR una base sobre PostgreSQL 15 (usa any_value()), así
# que la base v1 se crea en un PostgreSQL 17 de paso y se vuelca a la 15, que
# es como quedó la demo real: creada antes y servida por Odoo 20 sobre la 15.
#   uso: sudo env MUEBLES_SNAPSHOT=... bash ci/ensayo_preparar_demo_v1.sh <carpeta del checkout de la PR>
set -euo pipefail
PR_SRC="$1"
REF_V1=5ec6960ab157d3790f97986a3b74713a29bf0a5c
SNAPSHOT="${MUEBLES_SNAPSHOT:?}"

echo "==> Repositorio en /root/ODOO_CRM, rama main en la v1"
git clone -q "https://github.com/kavanasystemsinfo-ui/ODOO_CRM.git" /root/ODOO_CRM
git -C /root/ODOO_CRM checkout -q -B main "$REF_V1"
git -C /root/ODOO_CRM remote add pr "$PR_SRC"
git -C /root/ODOO_CRM fetch -q pr

echo "==> Base v1 creada en un PostgreSQL 17 de paso"
docker network create ensayo >/dev/null
docker run -d --name pg_paso --network ensayo -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo postgres:17 >/dev/null
until docker exec pg_paso pg_isready -U odoo >/dev/null 2>&1; do sleep 2; done
mkdir -p /tmp/v1 && git -C /root/ODOO_CRM worktree add -q /tmp/v1/ODOO_CRM "$REF_V1"
docker run --rm --network ensayo -e HOST=pg_paso -e USER=odoo -e PASSWORD=odoo \
  -v /tmp/v1:/mnt/extra-addons:ro odoo:20 odoo -d furniture_db -i ODOO_CRM --stop-after-init > /tmp/v1_instalar.log 2>&1 \
  || { tail -30 /tmp/v1_instalar.log; exit 1; }
docker run --rm -i --network ensayo -e HOST=pg_paso -e USER=odoo -e PASSWORD=odoo \
  -v /tmp/v1:/mnt/extra-addons:ro odoo:20 odoo shell -d furniture_db --no-http \
  < "$PR_SRC/ci/sembrar_v1.py" | grep SIEMBRA_V1_OK
# Usuario de visita, como en la demo (la v2 le cambia la contraseña).
docker run --rm -i --network ensayo -e HOST=pg_paso -e USER=odoo -e PASSWORD=odoo \
  -v /tmp/v1:/mnt/extra-addons:ro odoo:20 odoo shell -d furniture_db --no-http <<'PY' | grep VISITA_CREADA
env['res.users'].create({'name': 'Visita', 'login': 'visita', 'password': 'Visita-publicada-en-git'})
env.cr.commit()
print('VISITA_CREADA')
PY
docker exec pg_paso pg_dump -U odoo -d furniture_db --no-owner > /tmp/furniture_db_v1.sql

echo "==> La demo: compose v1 (PostgreSQL 15) con esa base"
docker compose -f /root/ODOO_CRM/docker-compose.yml up -d db
until docker exec furniture_db pg_isready -U odoo >/dev/null 2>&1; do sleep 2; done
for base in furniture_db muebles_plantilla; do
  docker exec furniture_db psql -q -U odoo -d postgres -c "CREATE DATABASE $base OWNER odoo TEMPLATE template0"
  # Un volcado de la 17 trae algún SET que la 15 no conoce: se ignora.
  docker exec -i furniture_db psql -q -U odoo -d "$base" < /tmp/furniture_db_v1.sql 2>&1 \
    | grep -v 'transaction_timeout' || true
done
docker exec furniture_db postgres --version
docker compose -f /root/ODOO_CRM/docker-compose.yml up -d odoo
for _ in $(seq 1 100); do curl -sf -o /dev/null http://127.0.0.1:8070/web/login && break; sleep 3; done
curl -sf -o /dev/null http://127.0.0.1:8070/web/login

echo "==> Instantánea canónica v1"
mkdir -p "$(dirname "$SNAPSHOT")"
docker exec furniture_db pg_dump -U odoo -d furniture_db | gzip > "$SNAPSHOT"
docker rm -f pg_paso >/dev/null
echo "DEMO_V1_LISTA"
