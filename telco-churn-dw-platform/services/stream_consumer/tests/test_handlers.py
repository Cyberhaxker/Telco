import json
import uuid

from stream_consumer.handlers import DlqRow, EventRow, handle

RECORD = {
    "customer_id": "9999-TESTA",
    "gender": "Female",
    "senior_citizen": 0,
    "partner": "Yes",
    "dependents": "No",
    "tenure_months": 5,
    "phone_service": "Yes",
    "multiple_lines": "No",
    "internet_service": "Fiber optic",
    "online_security": "No",
    "online_backup": "Yes",
    "device_protection": "No",
    "tech_support": "No",
    "streaming_tv": "Yes",
    "streaming_movies": "No",
    "contract_type": "Month-to-month",
    "paperless_billing": "Yes",
    "payment_method": "Electronic check",
    "monthly_charges": 80.5,
    "total_charges": 402.5,
    "churned": False,
}


def msg(**overrides):
    m = {
        "event_id": str(uuid.uuid4()),
        "event_type": "subscription.upserted",
        "schema_version": "1",
        "batch_id": str(uuid.uuid4()),
        "produced_at": "2026-10-21T10:00:00+00:00",
        "source": "ingestion-api",
        "payload": RECORD,
    }
    m.update(overrides)
    return json.dumps(m).encode()


def test_valid_event_becomes_row():
    row = handle("ingest.subscriptions.v1", 2, 41, msg())
    assert isinstance(row, EventRow)
    assert row.customer_id == "9999-TESTA" and row.partition == 2 and row.offset == 41


def test_invalid_json_goes_to_dlq():
    row = handle("ingest.customers.v1", 0, 1, b"{nope")
    assert isinstance(row, DlqRow) and row.error_code == "invalid_json"


def test_wrong_event_type_for_topic():
    row = handle("ingest.customers.v1", 0, 1, msg())
    assert isinstance(row, DlqRow) and row.error_code == "unexpected_event_type"


def test_invalid_record_goes_to_dlq():
    row = handle("ingest.subscriptions.v1", 0, 1, msg(payload={**RECORD, "gender": "X"}))
    assert isinstance(row, DlqRow) and row.error_code == "invalid_record" and "gender" in row.error_message


def test_unknown_schema_version():
    row = handle("ingest.subscriptions.v1", 0, 1, msg(schema_version="2"))
    assert isinstance(row, DlqRow) and row.error_code == "unsupported_schema_version"


def test_rejected_records_are_landed_from_dlq_topic():
    value = msg(event_type="record.rejected", payload={"row": 3, "errors": [{"field": "gender"}]})
    row = handle("ingest.dlq.v1", 0, 7, value)
    assert isinstance(row, DlqRow) and row.error_code == "rejected_at_ingestion"
