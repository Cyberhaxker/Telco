# Licences

Only OSI-approved open-source licences. No component needs a commercial licence key, and no SaaS service is required.

## Runtime services (container images)

| Component | Version | Licence |
|---|---|---|
| PostgreSQL | 18.6 | PostgreSQL Licence |
| MySQL Community Server | 8.4.9 LTS | GPLv2 (standalone server) |
| Apache Kafka (KRaft) | 4.2.2 | Apache 2.0 |
| Apache APISIX | 3.19.0 | Apache 2.0 |
| Keycloak | 26.7.5 | Apache 2.0 |
| Apache Airflow | 3.3.2 | Apache 2.0 |
| MLflow | 3.16.1 | Apache 2.0 |
| Valkey | 8.1.10 | BSD-3-Clause |
| NGINX (open source) | 1.30.5 | BSD-2-Clause |
| Prometheus | 3.13.5 | Apache 2.0 |
| Grafana OSS | 13.0.2 | AGPLv3 (unmodified standalone server) |
| Grafana Loki | 3.7.8 | AGPLv3 (unmodified standalone server) |
| Grafana Alloy | 1.20.1 | Apache 2.0 |
| postgres_exporter | 0.19.1 | Apache 2.0 |
| mysqld_exporter | 0.20.0 | Apache 2.0 |
| kafka_exporter | 1.9.0 | Apache 2.0 |
| statsd_exporter | 0.31.0 | Apache 2.0 |
| Python base image | 3.12.15-slim | PSF |
| Node.js (build only) | 22.23.3 | MIT |

## Python libraries

| Library | Licence |
|---|---|
| FastAPI, Pydantic, pydantic-settings, Starlette, Uvicorn | MIT / BSD-3-Clause |
| SQLAlchemy, Alembic | MIT |
| PyMySQL | MIT |
| psycopg 3, psycopg-pool | LGPL-3.0 (dynamically linked library) |
| psycopg2-binary | LGPL-3.0 (dbt adapter dependency) |
| aiokafka | Apache 2.0 |
| confluent-kafka-python (client only) | Apache 2.0 |
| lz4 | BSD-3-Clause |
| PyJWT, cryptography | MIT / Apache 2.0 or BSD |
| jsonschema, referencing | MIT |
| prometheus-client, prometheus-fastapi-instrumentator | Apache 2.0 / ISC |
| redis-py | MIT |
| httpx | BSD-3-Clause |
| pandas, NumPy, scikit-learn, joblib | BSD-3-Clause |
| mlflow-skinny | Apache 2.0 |
| skops (safe model serialisation used by MLflow) | MIT |
| dbt-core, dbt-postgres | Apache 2.0 |
| pytest, pytest-cov, ruff, mypy | MIT |

## JavaScript libraries (PWA)

| Library | Licence |
|---|---|
| Next.js, React | MIT |
| Serwist (@serwist/next, serwist) | MIT |
| Dexie.js | Apache 2.0 |
| Apache ECharts | Apache 2.0 |
| TanStack Table | MIT |
| oidc-client-ts | Apache 2.0 |
| Ajv, ajv-formats | MIT |
| Papa Parse | MIT |
| Vitest, Testing Library, Playwright, ESLint, Prettier, TypeScript | MIT / Apache 2.0 |

Fonts: Instrument Sans and JetBrains Mono (SIL Open Font Licence 1.1), self-hosted at build time.

## Notes

- The platform uses the open-source Confluent **client library** (`confluent-kafka`, Apache 2.0) but not Confluent Platform or Confluent Server.
- dbt runs as dbt Core; dbt Cloud and dbt Fusion are not used.
- AGPL components (Grafana, Loki) run unmodified as separate services, so the AGPL does not extend to this code.
