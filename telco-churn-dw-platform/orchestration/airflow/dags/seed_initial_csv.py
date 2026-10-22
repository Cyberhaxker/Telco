"""Validate the IBM CSV and load it into the MySQL operational database (manual trigger)."""

from __future__ import annotations

from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG
from telco_dag_defaults import DEFAULT_ARGS, ETL_PY

with DAG(
    dag_id="seed_initial_csv",
    description="Validate CSV against the record contract, load telco_ops, record the batch",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["telco", "seed"],
) as dag:
    validate = BashOperator(task_id="validate_csv", bash_command=f"{ETL_PY} -m pipelines.seed_csv --validate-only")
    load = BashOperator(task_id="load_mysql", bash_command=f"{ETL_PY} -m pipelines.seed_csv")
    validate >> load
