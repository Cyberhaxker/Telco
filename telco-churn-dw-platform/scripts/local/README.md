# Running without Docker

For machines with a local PostgreSQL 18 (warehouse), MySQL (operational DB) and Node 22, but no Docker.
APISIX, Kafka, Airflow and MLflow are replaced by `gateway.py`, direct
writes and local model files, so `GET /meta/pipelines` returns 503 (no Airflow) and batches stay
`VALIDATED` (no Kafka to publish to).

```bash
python -m venv .venv && .venv/bin/pip install -e libs/common_py -e ml -e services/analytics_api \
    -e services/metadata_api -e services/ingestion_api "psycopg[binary]" psycopg-pool "uvicorn[standard]" \
    redis sqlalchemy pymysql alembic python-multipart scikit-learn pandas
python -m venv /tmp/dbtvenv && /tmp/dbtvenv/bin/pip install dbt-core dbt-postgres   # DBT=/tmp/dbtvenv/bin/dbt below

DBT=/tmp/dbtvenv/bin/dbt scripts/local/bootstrap-dw.sh      # roles, schemas, seed, dbt build (78 nodes)
DBT=/tmp/dbtvenv/bin/dbt scripts/local/train-and-score.sh   # models -> ml.*, rebuilds olap.*
scripts/local/run-apis.sh                                   # ingestion :8001, meta :8002, analytics :8003, gateway :9080
node apps/web/scripts/seed-users.mjs                           # once: telco_ops.app_users + one account per role (passwords printed)
scripts/local/run-web.sh                                    # Next.js on :3000 (login routes + UI)
```

`telco_ops` (MySQL) needs the `ops_app` user from `infra/db/mysql/init/01_users.sh` before `run-apis.sh`.
The dashboard streams `GET /api/v1/analytics/stream` (server-sent events) and falls back to `GET /analytics/charts`.

Sign-in is the web app's own: `POST /api/auth/login` checks a bcrypt hash in `telco_ops.app_users` and issues an
httpOnly session cookie plus a 15-minute HS256 JWT. The APIs verify that JWT with the shared `JWT_SECRET` from `.env`
(roles come from the `roles` claim). Self-service registration creates viewer accounts; change roles with SQL, e.g.
`UPDATE app_users SET roles='analyst' WHERE username='ann'`. Because login needs the Next.js server, the app is no longer a static export.
