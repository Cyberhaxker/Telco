# MLflow tracking server + model registry (metadata in PostgreSQL, artifacts on a volume).
FROM python:3.12.15-slim
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONUNBUFFERED=1
RUN pip install "mlflow==3.16.1" "psycopg2-binary>=2.9,<3" \
 && groupadd --system --gid 50000 mlflow && useradd --system --uid 50000 --gid mlflow --create-home mlflow \
 && mkdir -p /mlartifacts && chown mlflow:mlflow /mlartifacts
USER mlflow
EXPOSE 5000
CMD ["sh", "-c", "exec mlflow server --backend-store-uri \"$MLFLOW_BACKEND_STORE_URI\" --artifacts-destination /mlartifacts --serve-artifacts --host 0.0.0.0 --port 5000 --workers ${MLFLOW_WORKERS:-1} ${MLFLOW_EXTRA_ARGS:-}"]
