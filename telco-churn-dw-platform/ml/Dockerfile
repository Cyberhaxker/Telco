# Training / scoring jobs (run by Airflow or `make train`).
FROM python:3.12.15-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY ml /src/ml
RUN python -m venv /opt/venv && /opt/venv/bin/pip install "/src/ml[tracking]"

FROM python:3.12.15-slim
LABEL org.opencontainers.image.title="telco-ml" org.opencontainers.image.licenses="MIT"
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ML_MODEL_DIR=/models
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 50000 ml && useradd --system --uid 50000 --gid ml --create-home ml \
 && mkdir -p /models && chown ml:ml /models
COPY --from=build /opt/venv /opt/venv
WORKDIR /home/ml
USER ml
CMD ["python", "-m", "telco_ml.train"]
