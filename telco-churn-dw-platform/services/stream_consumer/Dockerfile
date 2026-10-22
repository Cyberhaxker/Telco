# syntax=docker/dockerfile:1.7
FROM python:3.12.15-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY libs/common_py /src/libs/common_py
COPY services/stream_consumer /src/services/stream_consumer
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install /src/libs/common_py /src/services/stream_consumer

FROM python:3.12.15-slim
LABEL org.opencontainers.image.title="telco-stream-consumer" org.opencontainers.image.licenses="MIT"
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CONTRACTS_DIR=/app/contracts
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
COPY --from=build /opt/venv /opt/venv
COPY contracts /app/contracts
WORKDIR /app
USER app
EXPOSE 8001
CMD ["python", "-m", "stream_consumer.main"]
