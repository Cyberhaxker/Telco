from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ingestion_api.config import Settings
from ingestion_api.main import build_app
from ingestion_api.models import Base, EventOutbox, IngestionBatch
from ingestion_api.outbox import relay_once
from telco_common.auth import Principal, get_principal

ROOT = Path(__file__).resolve().parents[3]

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


class FakePublisher:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str, dict]] = []
        self.fail = fail

    def publish(self, messages):
        out = {}
        for topic, key, value, event_id in messages:
            if self.fail:
                out[event_id] = "broker unavailable"
            else:
                self.sent.append((topic, key, json.loads(value)))
                out[event_id] = None
        return out

    def close(self) -> None:
        pass


@pytest.fixture
def app(tmp_path):
    settings = Settings(ops_database_url=f"sqlite:///{tmp_path / 'ops.db'}", auth_disabled=True, kafka_enabled=False)
    application = build_app(settings)
    Base.metadata.create_all(application.state.engine)
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def batch_request(records, *, batch_id=None, key=None):
    body = json.dumps(
        {
            "batch_id": batch_id or str(uuid.uuid4()),
            "client_id": "test-device",
            "created_at": "2026-10-21T10:00:00Z",
            "source": "form",
            "records": records,
        },
        separators=(",", ":"),
    ).encode()
    headers = {
        "Idempotency-Key": key or str(uuid.uuid4()),
        "X-Checksum-SHA256": hashlib.sha256(body).hexdigest(),
        "Content-Type": "application/json",
    }
    return body, headers


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200


def test_batch_accepts_valid_and_reports_row_errors(client, app):
    bad = {**RECORD, "customer_id": "9999-TESTB", "total_charges": 1.0}
    body, headers = batch_request([RECORD, bad])
    r = client.post("/api/v1/ingest/batches", content=body, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "VALIDATED" and data["outcome"] == "PARTIAL"
    assert data["accepted_count"] == 1 and data["rejected_count"] == 1
    assert data["errors"] == [
        {
            "row": 1,
            "field": "total_charges",
            "code": "lt_monthly",
            "message": "total_charges must be >= monthly_charges when tenure_months > 0",
        }
    ]
    # One record event and one DLQ event are waiting in the outbox.
    pub = FakePublisher()
    assert relay_once(app.state.session_factory, pub) == 2
    topics = sorted(t for t, _, _ in pub.sent)
    assert topics == ["ingest.dlq.v1", "ingest.subscriptions.v1"]
    with app.state.session_factory() as s:
        assert s.get(IngestionBatch, data["batch_id"]).status == "PUBLISHED"


def test_resending_same_key_returns_original_result_without_duplicates(client, app):
    body, headers = batch_request([RECORD])
    first = client.post("/api/v1/ingest/batches", content=body, headers=headers).json()
    second = client.post("/api/v1/ingest/batches", content=body, headers=headers).json()
    assert second["replayed"] is True
    assert second["batch_id"] == first["batch_id"] and second["accepted_count"] == 1
    with app.state.session_factory() as s:
        assert s.query(EventOutbox).count() == 1
    assert client.get("/api/v1/ingest/customers").json()["total"] == 1


def test_same_key_different_payload_is_rejected(client):
    body, headers = batch_request([RECORD])
    client.post("/api/v1/ingest/batches", content=body, headers=headers)
    body2, headers2 = batch_request([{**RECORD, "monthly_charges": 81.0}], key=headers["Idempotency-Key"])
    r = client.post("/api/v1/ingest/batches", content=body2, headers=headers2)
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_checksum_mismatch_is_rejected(client):
    body, headers = batch_request([RECORD])
    headers["X-Checksum-SHA256"] = "0" * 64
    r = client.post("/api/v1/ingest/batches", content=body, headers=headers)
    assert r.status_code == 400 and "checksum" in r.json()["type"]


def test_more_than_500_records_rejected(client):
    body, headers = batch_request([RECORD] * 501)
    assert client.post("/api/v1/ingest/batches", content=body, headers=headers).status_code == 413


def test_stale_version_is_reported_as_conflict(client):
    body, headers = batch_request([RECORD])
    client.post("/api/v1/ingest/batches", content=body, headers=headers)
    # Server is now at version 1; a change from a client that saw version 1 succeeds ...
    body, headers = batch_request([{**RECORD, "monthly_charges": 85.0, "total_charges": 425.0, "version": 1}])
    assert client.post("/api/v1/ingest/batches", content=body, headers=headers).json()["accepted_count"] == 1
    # ... and a second client still on version 1 gets a conflict (server wins).
    body, headers = batch_request([{**RECORD, "monthly_charges": 90.0, "total_charges": 450.0, "version": 1}])
    data = client.post("/api/v1/ingest/batches", content=body, headers=headers).json()
    assert data["accepted_count"] == 0 and data["outcome"] == "REJECTED"
    assert data["conflicts"][0]["server_version"] == 2 and data["conflicts"][0]["client_version"] == 1
    assert data["conflicts"][0]["server_record"]["monthly_charges"] == 85.0


def test_unchanged_record_is_accepted_without_new_event(client, app):
    body, headers = batch_request([RECORD])
    client.post("/api/v1/ingest/batches", content=body, headers=headers)
    body, headers = batch_request([RECORD])  # new key, same data, stale version 0
    assert client.post("/api/v1/ingest/batches", content=body, headers=headers).json()["accepted_count"] == 1
    with app.state.session_factory() as s:
        assert s.query(EventOutbox).count() == 1


def test_duplicate_customer_in_one_batch(client):
    body, headers = batch_request([RECORD, RECORD])
    data = client.post("/api/v1/ingest/batches", content=body, headers=headers).json()
    assert data["accepted_count"] == 1 and data["errors"][0]["code"] == "duplicate_in_batch"


def test_customer_and_subscription_crud(client):
    r = client.post(
        "/api/v1/ingest/customers",
        json={"customer_id": "1111-CRUDA", "gender": "Male", "senior_citizen": 1, "partner": "No", "dependents": "No"},
    )
    assert r.status_code == 201 and r.json()["version"] == 1
    sub = {k: RECORD[k] for k in RECORD if k not in ("customer_id", "gender", "senior_citizen", "partner", "dependents")}
    r = client.post("/api/v1/ingest/subscriptions", json={"customer_id": "1111-CRUDA", "version": 1, **sub})
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 2 and r.json()["subscription"]["contract_type"] == "Month-to-month"
    r = client.put(
        "/api/v1/ingest/customers/1111-CRUDA",
        json={"gender": "Male", "senior_citizen": 1, "partner": "Yes", "dependents": "No", "version": 2},
    )
    assert r.status_code == 200 and r.json()["version"] == 3
    r = client.put(
        "/api/v1/ingest/customers/1111-CRUDA",
        json={"gender": "Male", "senior_citizen": 1, "partner": "No", "dependents": "No", "version": 2},
    )
    assert r.status_code == 409 and r.json()["conflicts"][0]["server_version"] == 3
    r = client.get("/api/v1/ingest/customers/1111-CRUDA")
    assert r.headers["etag"] == '"3"'


def test_subscription_business_rules_enforced(client):
    client.post(
        "/api/v1/ingest/customers",
        json={"customer_id": "2222-RULES", "gender": "Male", "senior_citizen": 0, "partner": "No", "dependents": "No"},
    )
    sub = {k: RECORD[k] for k in RECORD if k not in ("customer_id", "gender", "senior_citizen", "partner", "dependents")}
    sub["internet_service"] = "No"
    r = client.post("/api/v1/ingest/subscriptions", json={"customer_id": "2222-RULES", "version": 1, **sub})
    assert r.status_code == 422
    assert {e["field"] for e in r.json()["errors"]} >= {"online_security"}


def test_csv_upload_is_chunked_and_idempotent(client):
    csv_bytes = (ROOT / "data/raw/Telco-Customer-Churn.csv").read_bytes()
    head = b"\n".join(csv_bytes.splitlines()[:1201]) + b"\n"  # header + 1,200 rows -> 3 batches
    r = client.post("/api/v1/ingest/upload-csv", files={"file": ("telco.csv", head, "text/csv")})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["row_count"] == 1200 and len(data["batches"]) == 3
    assert data["accepted_count"] == 1200 and data["rejected_count"] == 0
    again = client.post("/api/v1/ingest/upload-csv", files={"file": ("telco.csv", head, "text/csv")}).json()
    assert all(b["replayed"] for b in again["batches"])
    assert client.get("/api/v1/ingest/customers?limit=1").json()["total"] == 1200


def test_csv_upload_reports_file_level_row_numbers(client):
    header = ",".join(
        [
            "customerID",
            "gender",
            "SeniorCitizen",
            "Partner",
            "Dependents",
            "tenure",
            "PhoneService",
            "MultipleLines",
            "InternetService",
            "OnlineSecurity",
            "OnlineBackup",
            "DeviceProtection",
            "TechSupport",
            "StreamingTV",
            "StreamingMovies",
            "Contract",
            "PaperlessBilling",
            "PaymentMethod",
            "MonthlyCharges",
            "TotalCharges",
            "Churn",
        ]
    )
    good = "0001-GOODA,Female,0,Yes,No,1,No,No phone service,DSL,No,Yes,No,No,No,No,Month-to-month,Yes,Electronic check,29.85,29.85,No"
    bad = "0002-BADXX,Robot,0,Yes,No,1,No,No phone service,DSL,No,Yes,No,No,No,No,Month-to-month,Yes,Electronic check,29.85,29.85,No"
    content = "\n".join([header, good, bad]).encode()
    data = client.post("/api/v1/ingest/upload-csv", files={"file": ("x.csv", content, "text/csv")}).json()
    assert data["accepted_count"] == 1
    assert data["batches"][0]["errors"][0]["row"] == 1 and data["batches"][0]["errors"][0]["field"] == "gender"


def test_outbox_keeps_events_when_kafka_is_down(client, app):
    body, headers = batch_request([RECORD])
    batch_id = client.post("/api/v1/ingest/batches", content=body, headers=headers).json()["batch_id"]
    assert relay_once(app.state.session_factory, FakePublisher(fail=True)) == 0
    with app.state.session_factory() as s:
        row = s.query(EventOutbox).one()
        assert row.published_at is None and row.attempts == 1 and row.last_error == "broker unavailable"
        assert s.get(IngestionBatch, batch_id).status == "VALIDATED"
    assert relay_once(app.state.session_factory, FakePublisher()) == 1


def test_role_guards(app):
    app.dependency_overrides[get_principal] = lambda: Principal("u1", "viewer", frozenset({"viewer"}))
    with TestClient(app) as c:
        body, headers = batch_request([RECORD])
        r = c.post("/api/v1/ingest/batches", content=body, headers=headers)
        assert r.status_code == 403 and r.json()["required_roles"] == ["data_entry"]
        assert c.get("/api/v1/ingest/customers").status_code == 403
    app.dependency_overrides.clear()


def test_missing_token_is_401(tmp_path):
    settings = Settings(ops_database_url=f"sqlite:///{tmp_path / 'ops.db'}", auth_disabled=False, kafka_enabled=False)
    with TestClient(build_app(settings)) as c:
        r = c.get("/api/v1/ingest/customers")
        assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Bearer")
