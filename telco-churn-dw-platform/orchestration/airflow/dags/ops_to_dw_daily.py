"""Daily warehouse refresh: MySQL -> raw -> dbt (staging/intermediate/marts/olap) -> quality -> event."""

from __future__ import annotations

from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG
from telco_dag_defaults import DBT, DBT_DIR, DBT_PY, DEFAULT_ARGS, ETL_PY, WAREHOUSE_REFRESHED

with DAG(
    dag_id="ops_to_dw_daily",
    description="Incremental extract, dbt build + tests, OLAP refresh, data-quality publication, dw.refreshed event",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["telco", "warehouse"],
) as dag:
    extract = BashOperator(task_id="extract_mysql_to_raw", bash_command=f"{ETL_PY} -m pipelines.extract_ops")
    dbt_build = BashOperator(
        task_id="dbt_build", cwd=DBT_DIR, bash_command=f"DBT={DBT} bash scripts/build.sh "
    )  # trailing space: not a template file
    refresh = BashOperator(task_id="refresh_olap_views", cwd=DBT_DIR, bash_command=f"{DBT_PY} scripts/refresh_olap.py")
    quality = BashOperator(
        task_id="publish_data_quality",
        cwd=DBT_DIR,
        bash_command=f"{DBT_PY} scripts/publish_dq.py && {DBT_PY} scripts/reconcile.py",
    )
    event = BashOperator(
        task_id="emit_dw_refreshed", outlets=[WAREHOUSE_REFRESHED], bash_command=f"{ETL_PY} -m pipelines.emit_event dw.refreshed"
    )
    extract >> dbt_build >> refresh >> quality >> event
