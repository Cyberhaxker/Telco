# Contracts

JSON Schema (draft 2020-12) files shared by every producer and consumer:

| File | Used by |
|------|---------|
| `telco-record.v1.schema.json` | PWA forms + CSV preview (Ajv), ingestion-api (jsonschema + Pydantic), stream-consumer |
| `ingest-batch.v1.schema.json` | PWA outbox, `POST /api/v1/ingest/batches` |
| `ingest-batch-result.v1.schema.json` | ingestion-api response, PWA `/sync` page |
| `kafka-envelope.v1.schema.json` | ingestion-api producer, stream-consumer, Airflow `dw.events.v1` emitter |

Rules that JSON Schema cannot express live in code and are mirrored on both
sides (`libs/common_py/telco_common/records.py`, `apps/web/src/lib/validation.ts`):

* `total_charges >= monthly_charges` when `tenure_months > 0`
* `total_charges` may be `null` only when `tenure_months == 0`

Breaking changes get a new `.v2` file and new topic names (`ingest.customers.v2`);
never edit a published version in place.
