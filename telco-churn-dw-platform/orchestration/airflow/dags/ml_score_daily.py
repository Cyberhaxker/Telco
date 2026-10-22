"""Daily scoring, triggered when ops_to_dw_daily has refreshed the warehouse."""

from __future__ import annotations

from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG
from telco_dag_defaults import DBT, DBT_DIR, DEFAULT_ARGS, ML_PREFIX, ML_PY, WAREHOUSE_REFRESHED

with DAG(
    dag_id="ml_score_daily",
    description="Score current customers with the champion, update fact churn_probability, refresh OLAP",
    schedule=[WAREHOUSE_REFRESHED],
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["telco", "ml"],
) as dag:
    score = BashOperator(task_id="score_customers", bash_command=f"{ML_PREFIX}{ML_PY} -m telco_ml.score")
    # Scores changed fact.churn_probability: rebuild the flat OLAP table and its aggregates.
    refresh = BashOperator(task_id="refresh_olap", cwd=DBT_DIR, bash_command=f"{DBT} run --select churn_flat+")
    score >> refresh
