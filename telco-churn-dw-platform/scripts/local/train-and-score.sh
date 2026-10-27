#!/usr/bin/env bash
# Docker-free equivalent of `make train`: train the four models, promote the champion
# locally (no MLflow), score every customer into ml.current_predictions, then rebuild the
# OLAP layer so olap.churn_flat carries the new probabilities.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
unset MLFLOW_TRACKING_URI
export DW_HOST="${DW_HOST:-127.0.0.1}" DW_PORT="${DW_PORT:-5433}"
PY="${PY:-$PWD/.venv/bin/python}"
export DW_DSN="postgresql://dw_ml:${DW_ML_PASSWORD}@${DW_HOST}:${DW_PORT}/${DW_DB}" ML_MODEL_DIR="$PWD/ml/artifacts"
"$PY" -m telco_ml.train
"$PY" -m telco_ml.score
export DBT_TARGET_PATH="${DBT_TARGET_PATH:-/tmp/telco-dbt-target}" DBT_LOG_PATH="${DBT_LOG_PATH:-/tmp/telco-dbt-logs}"
(cd transform/dbt_telco && DBT_PROFILES_DIR=. "${DBT:-dbt}" build --select olap)
