"""Shared defaults for the Telco DAGs: retries with exponential backoff and failure alerts."""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import timedelta
from typing import Any

from airflow.sdk import Asset

log = logging.getLogger(__name__)

ETL_PY = "/opt/etl-venv/bin/python"
ML_PY = "/opt/ml-venv/bin/python"
DBT = "/opt/dbt-venv/bin/dbt"
DBT_PY = "/opt/dbt-venv/bin/python"
DBT_DIR = os.environ.get("DBT_PROJECT_DIR", "/opt/airflow/dbt_telco")

WAREHOUSE_REFRESHED = Asset("postgres://dw-postgres/telco_churn_dw/marts/fact_customer_churn")

# Tasks inherit the worker's environment (connections and secrets are set on the
# container). Nothing secret is passed at parse time, so nothing secret ends up
# in the serialized DAG or the UI.
ML_PREFIX = 'export DW_DSN="$DW_ML_DSN"; '  # ML jobs run as the least-privileged dw_ml role


def alert_on_failure(context: dict[str, Any]) -> None:
    ti = context.get("task_instance")
    message = {
        "text": f"Airflow task failed: {getattr(ti, 'dag_id', '?')}.{getattr(ti, 'task_id', '?')}",
        "dag_id": getattr(ti, "dag_id", None),
        "task_id": getattr(ti, "task_id", None),
        "run_id": context.get("run_id"),
        "try_number": getattr(ti, "try_number", None),
        "exception": str(context.get("exception"))[:1000],
    }
    log.error("task failure: %s", message)
    url = os.environ.get("ALERT_WEBHOOK_URL")
    if url:
        try:
            req = urllib.request.Request(  # noqa: S310 - operator-configured https webhook
                url, data=json.dumps(message).encode(), headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)  # noqa: S310 - operator-configured URL
        except Exception as exc:  # noqa: BLE001 - alerting must never fail the callback
            log.warning("could not send failure alert: %s", exc)


DEFAULT_ARGS: dict[str, Any] = {
    "owner": "data-platform",
    "retries": 3,
    "retry_delay": timedelta(minutes=1),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(hours=1),
    "on_failure_callback": alert_on_failure,
}
if os.environ.get("ALERT_EMAIL"):
    DEFAULT_ARGS.update(email=[os.environ["ALERT_EMAIL"]], email_on_failure=True)
