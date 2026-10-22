# APIs

All endpoints sit behind APISIX at `PUBLIC_GATEWAY_URL` (also reachable same-origin from the PWA at `/api`). Every request needs a Keycloak bearer token; errors use RFC 9457 `application/problem+json`. List endpoints take `limit` (1–500) and `offset` and return `{items, total, limit, offset}`. Every service exposes `/healthz`, `/readyz` and `/metrics` inside the network.

Interactive OpenAPI docs (no token needed to read them):

- Metadata — `/api/v1/meta/docs`
- Ingestion — `/api/v1/ingest/docs`
- Analytics — `/api/v1/analytics/docs`

## metadata-api

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/api/v1/meta/datasets?layer=` | viewer | dataset registry with row counts and refresh times |
| GET | `/api/v1/meta/dictionary?table=&search=` | viewer | `ETag` / `If-None-Match` supported (304) |
| PUT | `/api/v1/meta/dictionary/{column_id}` | data_steward | optimistic locking on `version`; audited |
| GET | `/api/v1/meta/lineage/{model}?depth=` | viewer | upstream/downstream from the dbt manifest |
| GET | `/api/v1/meta/quality/runs?source=` | viewer | dbt test runs and reconciliation runs |
| GET | `/api/v1/meta/quality/runs/{run_id}` | viewer | individual check results |
| GET | `/api/v1/meta/dimensions/{dimension}/members` | viewer | whitelisted dimensions only |
| GET | `/api/v1/meta/pipelines` | data_steward | Airflow DAG state and recent runs |

## ingestion-api

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/api/v1/ingest/customers?search=` | data_entry, data_steward | |
| GET | `/api/v1/ingest/customers/{id}` | data_entry, data_steward | `ETag` = version |
| POST | `/api/v1/ingest/customers` | data_entry | 409 if it exists |
| PUT | `/api/v1/ingest/customers/{id}` | data_entry | body includes `version`; 409 with the server record on conflict |
| GET | `/api/v1/ingest/subscriptions?customer_id=` | data_entry, data_steward | |
| POST | `/api/v1/ingest/subscriptions` | data_entry | full business-rule validation |
| PUT | `/api/v1/ingest/subscriptions/{customer_id}` | data_entry | |
| POST | `/api/v1/ingest/batches` | data_entry | see below |
| GET | `/api/v1/ingest/batches/{batch_id}` | data_entry, data_steward | stored result |
| GET | `/api/v1/ingest/batches?status=&with_rejections=` | data_entry, data_steward | review queue |
| POST | `/api/v1/ingest/upload-csv` | data_entry | multipart; split into batches of 500; re-uploading the same file is idempotent |

### POST /api/v1/ingest/batches

Headers: `Idempotency-Key: <uuid>`, `X-Checksum-SHA256: <hex sha256 of the exact body>`. Body: [`contracts/ingest-batch.v1.schema.json`](../contracts/ingest-batch.v1.schema.json), at most 500 records and 5 MB.

```json
{
  "batch_id": "7d1c…", "status": "VALIDATED", "outcome": "PARTIAL",
  "accepted_count": 2, "rejected_count": 1, "replayed": false,
  "errors": [{ "row": 2, "field": "total_charges", "code": "lt_monthly",
               "message": "total_charges must be >= monthly_charges when tenure_months > 0" }],
  "conflicts": [{ "row": 0, "customer_id": "7590-VHVEG", "server_version": 3, "client_version": 2, "server_record": { … } }]
}
```

| Situation | Response |
|---|---|
| Same key, same body | 200 with the original result and `replayed: true` |
| Same key, different body | 422 `idempotency-key-reuse` |
| Checksum does not match | 400 `checksum-mismatch` |
| More than 500 records / 5 MB | 413 |
| Batch still being processed | 409 with `Retry-After` |
| Stale `version` | row listed in `conflicts`; server version kept |

`status` moves `RECEIVED → VALIDATED → PUBLISHED` once all its Kafka events are delivered.

## analytics-api

| Method | Path | Role | Notes |
|---|---|---|---|
| GET | `/api/v1/analytics/kpis` | viewer | totals, churn rate, high-risk count, breakdowns |
| GET | `/api/v1/analytics/olap/dimensions` | analyst | dimension members and allowed measures |
| POST | `/api/v1/analytics/olap/query` | analyst | see [olap-guide.md](olap-guide.md) |
| GET | `/api/v1/analytics/predictions?risk=&contract_type=&min_probability=&sort=` | analyst | active customers by default |
| GET | `/api/v1/analytics/predictions/{customer_id}` | analyst | attributes + top factors |
| POST | `/api/v1/analytics/predict` | analyst | ad-hoc profile (no protected attributes) |
| GET | `/api/v1/analytics/models` | analyst | latest training run, champion, fairness, drift, baseline |

GET responses are cached for 60 s by APISIX (keyed per token) and KPI/OLAP results for 60 s in Valkey.
