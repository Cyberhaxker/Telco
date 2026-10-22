#!/usr/bin/env bash
# One-shot: fix ownership of shared volumes, then migrate the Airflow metadata DB.
set -euo pipefail
mkdir -p /opt/airflow/logs /opt/airflow/dbt_artifacts/target /opt/airflow/dbt_artifacts/logs /models
chown -R 50000:0 /opt/airflow/logs /opt/airflow/dbt_artifacts /models
exec /usr/bin/dumb-init -- /opt/airflow/scripts/entrypoint.sh airflow db migrate
