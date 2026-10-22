# syntax=docker/dockerfile:1.7
FROM python:3.12.15-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY libs/common_py /src/libs/common_py
COPY services/metadata_api /src/services/metadata_api
RUN python -m venv /opt/venv && /opt/venv/bin/pip install /src/libs/common_py /src/services/metadata_api

FROM python:3.12.15-slim
LABEL org.opencontainers.image.title="telco-metadata-api" org.opencontainers.image.licenses="MIT"
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CONTRACTS_DIR=/app/contracts
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
COPY --from=build /opt/venv /opt/venv
COPY contracts /app/contracts
WORKDIR /app
USER app
EXPOSE 8000
CMD ["uvicorn", "--factory", "metadata_api.main:build_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
