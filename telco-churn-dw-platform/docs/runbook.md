# Runbook

All commands run from the repository root. `docker compose` uses `.env`; add `-f docker-compose.prod.yml` (and the profiles) for production.

## Health

| Check | Command |
|---|---|
| Container state | `make ps` |
| Gateway | `curl -s localhost:${APISIX_PORT}/healthz` |
| Service readiness | `docker compose exec analytics-api python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/readyz').read())"` |
| Warehouse freshness | Grafana → *Telco platform overview* → Data freshness, or `select * from meta.datasets order by last_refreshed_at;` |
| Data quality | PWA → Metadata → Data quality, or `select * from meta.dq_runs order by started_at desc limit 5;` |
| Pipelines | PWA → Admin, or Airflow UI at `localhost:${AIRFLOW_PORT}` |

Alert rules live in `infra/observability/prometheus/alerts.yml` (API errors and latency, consumer lag, stalled consumer, stale warehouse, Airflow failures, targets down).

## Backups

```bash
make dw-backup                      # full stack warehouse  -> backups/telco_churn_dw-<timestamp>.dump (+ .sha256)
make dw-backup STANDALONE=1         # standalone warehouse (project telco-dw)
```

The dump is written to a temporary name and renamed only on success, so a file in `backups/` is always complete. Schedule it (cron or a CI job) and copy `backups/` off the host. MySQL:

```bash
docker compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --routines --triggers telco_ops' | gzip > backups/telco_ops-$(date +%Y%m%dT%H%M%S).sql.gz
```

MLflow metadata lives in `platform-db` (database `mlflow`) and artifacts in the `mlflow-artifacts` volume. Back both up together.

## Restore

```bash
make dw-restore FILE=backups/telco_churn_dw-20261021T205906.dump
make dw-restore STANDALONE=1 FILE=…
```

The restore checks the checksum, disconnects other sessions, and runs `pg_restore --clean --if-exists --single-transaction` as the superuser. It either fully succeeds or leaves the warehouse unchanged. Stop Airflow first (`docker compose stop airflow-scheduler`) so no DAG writes during the restore. Afterwards run `make dbt-build` to make sure marts and OLAP match the restored raw data.

## Rotating secrets

1. Generate a new value: `head -c 48 /dev/urandom | base64 | tr -dc A-Za-z0-9 | head -c 32`.
2. Update it in the system that owns it, then in `.env`:

| Secret | Change it in | Then restart |
|---|---|---|
| `DW_*_PASSWORD` | `ALTER ROLE dw_x PASSWORD '…';` as the warehouse superuser | services using that role |
| `OPS_*_PASSWORD` | `ALTER USER 'ops_x'@'%' IDENTIFIED BY '…';` in MySQL | ingestion-api, Airflow, mysqld-exporter |
| `PLATFORM_DB_PASSWORD` | `ALTER ROLE airflow/keycloak/mlflow PASSWORD '…';` in platform-db | Airflow, Keycloak, MLflow |
| `KEYCLOAK_GATEWAY_CLIENT_SECRET` | Keycloak admin → Clients → telco-gateway → Credentials | apisix |
| `VALKEY_PASSWORD` | `.env` only | valkey, analytics-api, Airflow (prod) |
| `AIRFLOW_ADMIN_PASSWORD` | `.env` only (password file is rewritten at start) | Airflow services, metadata-api |
| `AIRFLOW_FERNET_KEY` | Put `new,old` in `AIRFLOW__CORE__FERNET_KEY`, run `airflow rotate-fernet-key`, then remove the old key | Airflow services |
| Demo user passwords | Keycloak admin console (the realm file is only imported on first start) | — |

3. `docker compose up -d <services>` to restart with the new values.

The realm import and the database init scripts only run on an empty volume. Changing `.env` alone never changes an existing password.

## Reprocessing the dead-letter queue

Rejected records land in two places: `telco_ops.ingestion_errors` (with the batch, for the person who submitted it) and `raw.ingest_dlq` (in the warehouse, via `ingest.dlq.v1`).

1. Find them: PWA → Sync (per device) or
   ```sql
   select error_code, count(*) from raw.ingest_dlq where reprocessed_at is null group by 1;
   select id, kafka_offset, error_message, raw_value from raw.ingest_dlq where reprocessed_at is null order by id limit 50;
   ```
2. **`rejected_at_ingestion`**: the record broke a validation rule. Correct it at the source and resubmit through the PWA or `POST /api/v1/ingest/batches` with a new Idempotency-Key. Then mark it handled:
   ```sql
   update raw.ingest_dlq set reprocessed_at = now() where id = any('{…}');
   ```
3. **`invalid_record`, `invalid_envelope`, `unsupported_schema_version`** (produced by stream-consumer): a producer sent something the contract rejects. Fix the producer. To replay the original messages once a fixed consumer is deployed, reset the consumer group offset to before the first bad message:
   ```bash
   docker compose stop stream-consumer
   docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
     --group dw-stream-consumer --topic ingest.subscriptions.v1 --reset-offsets --to-datetime 2026-10-21T00:00:00.000 --execute
   docker compose start stream-consumer
   ```
   Replays are safe: events are upserted on `event_id`.

## Re-running the pipeline

```bash
docker compose exec airflow-scheduler airflow dags trigger ops_to_dw_daily
docker compose exec airflow-scheduler /opt/etl-venv/bin/python -m pipelines.extract_ops --full   # ignore the watermark
make dbt-build
make train
```

## Outbox stuck in ingestion-api

Batches stay `VALIDATED` while their Kafka events are undelivered. Check `select count(*), max(last_error) from telco_ops.event_outbox where published_at is null;`. The relay retries with backoff until Kafka is reachable; no data is lost and nothing needs to be resent.
