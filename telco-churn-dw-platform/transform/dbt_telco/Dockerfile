# dbt Core + dbt-postgres for the telco warehouse (no dbt Cloud / Fusion).
FROM python:3.12.15-slim
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DBT_PROFILES_DIR=/app DBT_PROJECT_DIR=/app DBT_SEND_ANONYMOUS_USAGE_STATS=false DBT_TARGET_PATH=/dbt_artifacts/target \
    DBT_LOG_PATH=/dbt_artifacts/logs \
    DBT_PARTIAL_PARSE=false
RUN pip install "dbt-core==1.12.5" "dbt-postgres==1.11.0" "psycopg2-binary>=2.9,<3" \
 && groupadd --system --gid 50000 dbt && useradd --system --uid 50000 --gid dbt --create-home dbt \
 && mkdir -p /dbt_artifacts/target /dbt_artifacts/logs /app && chown -R dbt:dbt /dbt_artifacts /app
WORKDIR /app
COPY --chown=dbt:dbt transform/dbt_telco /app
USER dbt
ENTRYPOINT []
CMD ["dbt", "build"]
