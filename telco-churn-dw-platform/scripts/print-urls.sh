#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
cat <<EOF

Telco Churn Analytics Platform is up.

  PWA ............ ${PUBLIC_WEB_URL}
  API gateway .... ${PUBLIC_GATEWAY_URL}   (OpenAPI: /api/v1/{meta,ingest,analytics}/docs)
  Keycloak ....... ${PUBLIC_KEYCLOAK_URL}   (admin / see KEYCLOAK_ADMIN_PASSWORD in .env)
  Airflow ........ http://localhost:${AIRFLOW_PORT}
  MLflow ......... http://localhost:${MLFLOW_PORT}
  Grafana ........ http://localhost:${GRAFANA_PORT}
  Warehouse ...... postgresql://localhost:${POSTGRES_PORT}/${DW_DB}

Demo users (password = DEMO_USER_PASSWORD in .env):
  admin, steward, entry, analyst, viewer
EOF
