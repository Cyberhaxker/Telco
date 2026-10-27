#!/usr/bin/env bash
# Run the three HTTP APIs directly on the host (no Docker) against the local
# warehouse. Requests need a bearer token signed with JWT_SECRET (issued by the web
# app's login; see apps/web/scripts/seed-users.mjs for accounts). Ports: ingestion 8001, metadata 8002, analytics 8003.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
HOST="${DW_HOST:-127.0.0.1}"; PORT="${DW_PORT:-5433}"
PY="${PY:-$PWD/.venv/bin/python}"
export ENVIRONMENT=dev CORS_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
export DBT_MANIFEST_PATH=/tmp/telco-dbt-target/manifest.json ML_MODEL_DIR="$PWD/ml/artifacts" MLFLOW_TRACKING_URI=
LOGS="${LOGS:-/tmp/telco-logs}"; mkdir -p "$LOGS"

DW_DSN="postgresql://dw_analytics:${DW_ANALYTICS_PASSWORD}@${HOST}:${PORT}/${DW_DB}" \
  nohup "$PY" -m uvicorn --factory analytics_api.main:build_app --host 127.0.0.1 --port 8003 >"$LOGS/analytics.log" 2>&1 &
DW_DSN="postgresql://dw_meta:${DW_META_PASSWORD}@${HOST}:${PORT}/${DW_DB}" \
  nohup "$PY" -m uvicorn --factory metadata_api.main:build_app --host 127.0.0.1 --port 8002 >"$LOGS/metadata.log" 2>&1 &
export OPS_DATABASE_URL="mysql+pymysql://ops_app:${OPS_APP_PASSWORD}@127.0.0.1:${MYSQL_PORT_LOCAL:-3306}/${OPS_DB}"
(cd services/ingestion_api && "$PY" -m alembic -c alembic.ini upgrade head) 2>/dev/null || true
KAFKA_ENABLED=false \
  nohup "$PY" -m uvicorn --factory ingestion_api.main:build_app --host 127.0.0.1 --port 8001 >"$LOGS/ingestion.log" 2>&1 &
echo "APIs starting; logs in $LOGS"
nohup "$PY" scripts/local/gateway.py >"$LOGS/gateway.log" 2>&1 &
echo "gateway on http://localhost:9080 (/api/v1/{ingest,meta,analytics})"
