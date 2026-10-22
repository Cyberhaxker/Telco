"""Weekly training: rebuild features, train 4 models with stratified 5-fold CV, log to MLflow, promote if better."""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG
from telco_dag_defaults import DBT, DBT_DIR, DEFAULT_ARGS, ML_PREFIX, ML_PY

with DAG(
    dag_id="ml_train_weekly",
    description="Feature table, training, evaluation, MLflow logging and champion promotion",
    schedule="@weekly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={**DEFAULT_ARGS, "execution_timeout": timedelta(hours=2)},
    tags=["telco", "ml"],
) as dag:
    features = BashOperator(task_id="build_feature_table", cwd=DBT_DIR, bash_command=f"{DBT} run --select ml_features")
    train = BashOperator(task_id="train_evaluate_promote", bash_command=f"{ML_PREFIX}{ML_PY} -m telco_ml.train")
    features >> train
