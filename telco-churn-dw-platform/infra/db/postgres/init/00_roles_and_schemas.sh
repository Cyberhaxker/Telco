#!/usr/bin/env bash
# Least-privilege roles and the layered schemas of the warehouse.
set -euo pipefail

: "${DW_OWNER_PASSWORD:?DW_OWNER_PASSWORD is required}"
: "${DW_INGEST_PASSWORD:?DW_INGEST_PASSWORD is required}"
: "${DW_ANALYTICS_PASSWORD:?DW_ANALYTICS_PASSWORD is required}"
: "${DW_META_PASSWORD:?DW_META_PASSWORD is required}"
: "${DW_ML_PASSWORD:?DW_ML_PASSWORD is required}"
: "${DW_MONITOR_PASSWORD:?DW_MONITOR_PASSWORD is required}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v owner_pw="$DW_OWNER_PASSWORD" -v ingest_pw="$DW_INGEST_PASSWORD" \
  -v analytics_pw="$DW_ANALYTICS_PASSWORD" -v meta_pw="$DW_META_PASSWORD" -v ml_pw="$DW_ML_PASSWORD" \
  -v monitor_pw="$DW_MONITOR_PASSWORD" -v db="$POSTGRES_DB" <<'SQL'
CREATE ROLE dw_owner     LOGIN PASSWORD :'owner_pw';
CREATE ROLE dw_ingest    LOGIN PASSWORD :'ingest_pw'    CONNECTION LIMIT 20;
CREATE ROLE dw_analytics LOGIN PASSWORD :'analytics_pw' CONNECTION LIMIT 40;
CREATE ROLE dw_meta      LOGIN PASSWORD :'meta_pw'      CONNECTION LIMIT 20;
CREATE ROLE dw_ml        LOGIN PASSWORD :'ml_pw'        CONNECTION LIMIT 10;
-- Prometheus postgres-exporter: server statistics only, no data access.
CREATE ROLE dw_monitor   LOGIN PASSWORD :'monitor_pw'   CONNECTION LIMIT 3 IN ROLE pg_monitor;

ALTER ROLE dw_analytics SET default_transaction_read_only = on;
ALTER ROLE dw_analytics SET statement_timeout = '30s';
ALTER ROLE dw_meta SET statement_timeout = '30s';
ALTER ROLE dw_monitor SET statement_timeout = '10s';

REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO dw_owner, dw_ingest, dw_analytics, dw_meta, dw_ml, dw_monitor;
GRANT CREATE, TEMPORARY ON DATABASE :"db" TO dw_owner;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA raw          AUTHORIZATION dw_owner;
CREATE SCHEMA staging      AUTHORIZATION dw_owner;
CREATE SCHEMA intermediate AUTHORIZATION dw_owner;
CREATE SCHEMA snapshots    AUTHORIZATION dw_owner;
CREATE SCHEMA marts        AUTHORIZATION dw_owner;
CREATE SCHEMA olap         AUTHORIZATION dw_owner;
CREATE SCHEMA ml           AUTHORIZATION dw_owner;
CREATE SCHEMA meta         AUTHORIZATION dw_owner;

COMMENT ON SCHEMA raw          IS 'Landed data as-is (Airflow extract, Kafka consumer, CSV seed) with _loaded_at and _source';
COMMENT ON SCHEMA staging      IS 'dbt staging views: typing, renaming, cleaning';
COMMENT ON SCHEMA intermediate IS 'dbt joins and business logic';
COMMENT ON SCHEMA snapshots    IS 'dbt snapshots (SCD Type 2 history)';
COMMENT ON SCHEMA marts        IS 'Star schema: dimensions + fact_customer_churn';
COMMENT ON SCHEMA olap         IS 'Materialised views and aggregates for OLAP';
COMMENT ON SCHEMA ml           IS 'Feature tables, predictions, model run metadata';
COMMENT ON SCHEMA meta         IS 'Data dictionary, lineage, data-quality results';

-- Read paths
GRANT USAGE ON SCHEMA marts, olap, ml TO dw_analytics;
GRANT USAGE ON SCHEMA meta, marts, olap TO dw_meta;
GRANT USAGE ON SCHEMA ml, marts TO dw_ml;
GRANT USAGE ON SCHEMA raw TO dw_ingest;

-- Objects dbt creates later inherit these grants automatically.
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA marts GRANT SELECT ON TABLES TO dw_analytics, dw_meta, dw_ml;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA olap  GRANT SELECT ON TABLES TO dw_analytics, dw_meta;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA ml    GRANT SELECT ON TABLES TO dw_analytics;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA ml    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dw_ml;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA ml    GRANT USAGE, SELECT ON SEQUENCES TO dw_ml;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA meta  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dw_meta;
ALTER DEFAULT PRIVILEGES FOR ROLE dw_owner IN SCHEMA meta  GRANT USAGE, SELECT ON SEQUENCES TO dw_meta;
SQL
