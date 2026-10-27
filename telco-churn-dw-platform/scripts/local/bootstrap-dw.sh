#!/usr/bin/env bash
# Docker-free warehouse bootstrap for a locally installed PostgreSQL.
#
# Does what the packaged warehouse image does on first start (roles, layered
# schemas, raw/meta/ml tables, legacy star schema, CSV seed, data dictionary),
# then builds staging -> marts -> OLAP with dbt. Everything is additive: the
# existing `public` star schema of the database is left untouched. Idempotent.
#
# Usage: scripts/local/bootstrap-dw.sh        (reads .env; DW_HOST/DW_PORT override)
set -euo pipefail
cd "$(dirname "$0")/../.."

set -a; . ./.env; set +a
export DW_HOST="${DW_HOST:-127.0.0.1}" DW_PORT="${DW_PORT:-5433}"
export PGHOST="$DW_HOST" PGPORT="$DW_PORT" PGUSER="${DW_SUPERUSER:-postgres}" PGPASSWORD="${DW_SUPERUSER_PASSWORD:-}"
DB="${DW_DB:-telco_churn_dw}"
PSQL=(psql -v ON_ERROR_STOP=1 -X -q -d "$DB")
DBT_BIN="${DBT:-dbt}"

echo "== roles and schemas"
"${PSQL[@]}" \
  -v owner_pw="$DW_OWNER_PASSWORD" -v ingest_pw="$DW_INGEST_PASSWORD" -v analytics_pw="$DW_ANALYTICS_PASSWORD" \
  -v meta_pw="$DW_META_PASSWORD" -v ml_pw="$DW_ML_PASSWORD" -v db="$DB" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', r.n, r.pw)
FROM (VALUES ('dw_owner', :'owner_pw'), ('dw_ingest', :'ingest_pw'), ('dw_analytics', :'analytics_pw'),
             ('dw_meta', :'meta_pw'), ('dw_ml', :'ml_pw')) AS r(n, pw)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r.n)
\gexec
ALTER ROLE dw_analytics SET default_transaction_read_only = on;
ALTER ROLE dw_analytics SET statement_timeout = '30s';
ALTER ROLE dw_meta SET statement_timeout = '30s';
GRANT CONNECT ON DATABASE :"db" TO dw_owner, dw_ingest, dw_analytics, dw_meta, dw_ml;
GRANT CREATE, TEMPORARY ON DATABASE :"db" TO dw_owner;
-- pgcrypto is optional locally (gen_random_uuid is built in)

SELECT format('CREATE SCHEMA %I AUTHORIZATION dw_owner', s)
FROM unnest(ARRAY['raw','staging','intermediate','snapshots','marts','olap','ml','meta']) AS s
WHERE NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = s)
\gexec

GRANT USAGE ON SCHEMA marts, olap, ml TO dw_analytics;
GRANT USAGE ON SCHEMA meta, marts, olap TO dw_meta;
GRANT USAGE ON SCHEMA ml, marts TO dw_ml;
GRANT USAGE ON SCHEMA raw TO dw_ingest;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA marts GRANT SELECT ON TABLES TO dw_analytics, dw_meta, dw_ml;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA olap  GRANT SELECT ON TABLES TO dw_analytics, dw_meta;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA ml    GRANT SELECT ON TABLES TO dw_analytics;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA ml    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dw_ml;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA ml    GRANT USAGE, SELECT ON SEQUENCES TO dw_ml;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA meta  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dw_meta;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA meta  GRANT USAGE, SELECT ON SEQUENCES TO dw_meta;
SQL

exists() { "${PSQL[@]}" -tA -c "select to_regclass('$1') is not null" | grep -q t; }

if exists raw.telco_csv_seed; then
  echo "== raw/meta/ml tables already present"
else
  echo "== raw/meta/ml tables and CSV seed"
  "${PSQL[@]}" -f infra/db/postgres/init/10_dw_tables.sql
  "${PSQL[@]}" -c "\copy raw.telco_csv_seed (customer_id, gender, senior_citizen, partner, dependents, tenure, phone_service, multiple_lines, internet_service, online_security, online_backup, device_protection, tech_support, streaming_tv, streaming_movies, contract, paperless_billing, payment_method, monthly_charges, total_charges, churn) from 'data/raw/Telco-Customer-Churn.csv' with (format csv, header true)"
fi

if "${PSQL[@]}" -tA -c "select 1 from pg_namespace where nspname='legacy'" | grep -q 1; then
  echo "== legacy schema already present"
else
  echo "== legacy star schema"
  zcat infra/db/postgres/seed/20_telco_churn_dw_legacy.sql.gz | "${PSQL[@]}" -q >/dev/null
  "${PSQL[@]}" -c "GRANT USAGE ON SCHEMA legacy TO dw_owner, dw_analytics, dw_meta; GRANT SELECT ON ALL TABLES IN SCHEMA legacy TO dw_owner, dw_analytics, dw_meta;"
fi

if [ "$("${PSQL[@]}" -tA -c 'select count(*) from meta.datasets')" = 0 ]; then
  echo "== data dictionary and dataset registry"
  "${PSQL[@]}" -f infra/db/postgres/init/40_meta_seed.sql
fi

echo "== dbt build (staging -> marts -> olap)"
export DW_DB="$DB" DW_OWNER_PASSWORD DBT_TARGET_PATH="${DBT_TARGET_PATH:-/tmp/telco-dbt-target}" DBT_LOG_PATH="${DBT_LOG_PATH:-/tmp/telco-dbt-logs}"
(cd transform/dbt_telco && DBT="$DBT_BIN" DBT_PROFILES_DIR=. ./scripts/build.sh)

echo "== done"
