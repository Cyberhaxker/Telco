# Apache Airflow 3 with three isolated virtualenvs so task dependencies never
# conflict with Airflow's own: dbt (transformations), ML (training/scoring),
# ETL (seed/extract/events).
FROM apache/airflow:3.3.2-python3.12

USER root
RUN mkdir -p /opt/dbt-venv /opt/ml-venv /opt/etl-venv /src /models /opt/airflow/dbt_artifacts \
 && chown -R airflow:0 /opt/dbt-venv /opt/ml-venv /opt/etl-venv /src /models /opt/airflow/dbt_artifacts
USER airflow
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/dbt-venv && /opt/dbt-venv/bin/pip install "dbt-core==1.12.5" "dbt-postgres==1.11.0" "psycopg2-binary>=2.9,<3"

COPY --chown=airflow:0 ml /src/ml
RUN python -m venv /opt/ml-venv && /opt/ml-venv/bin/pip install "/src/ml[tracking]"

COPY --chown=airflow:0 libs/common_py /src/libs/common_py
COPY --chown=airflow:0 orchestration/airflow/pipelines /src/pipelines
RUN python -m venv /opt/etl-venv && /opt/etl-venv/bin/pip install /src/libs/common_py /src/pipelines

COPY --chown=airflow:0 contracts /opt/airflow/contracts
COPY --chown=airflow:0 transform/dbt_telco /opt/airflow/dbt_telco
COPY --chown=airflow:0 --chmod=755 orchestration/airflow/scripts /opt/airflow/scripts
COPY --chown=airflow:0 orchestration/airflow/dags /opt/airflow/dags

ENV CONTRACTS_DIR=/opt/airflow/contracts \
    DBT_PROJECT_DIR=/opt/airflow/dbt_telco DBT_PROFILES_DIR=/opt/airflow/dbt_telco \
    DBT_TARGET_PATH=/opt/airflow/dbt_artifacts/target DBT_LOG_PATH=/opt/airflow/dbt_artifacts/logs \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false DBT_PARTIAL_PARSE=false ML_MODEL_DIR=/models

ENTRYPOINT ["/usr/bin/dumb-init", "--", "/opt/airflow/scripts/entrypoint.sh"]
CMD []
