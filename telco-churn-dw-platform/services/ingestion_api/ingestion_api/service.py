"""Write path for operational records: validation, optimistic locking, audit and outbox."""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from telco_common.kafka import TOPIC_CUSTOMERS, TOPIC_DLQ, TOPIC_SUBSCRIPTIONS, envelope
from telco_common.problems import ProblemError
from telco_common.records import RECORD_FIELDS, RowError, TelcoRecord, validate_record

from .models import AuditLog, Customer, EventOutbox, IngestionBatch, IngestionError, Subscription, SubscriptionServices

log = logging.getLogger(__name__)

CUSTOMER_FIELDS = ("gender", "senior_citizen", "partner", "dependents")
SUBSCRIPTION_FIELDS = (
    "contract_type",
    "paperless_billing",
    "payment_method",
    "monthly_charges",
    "total_charges",
    "tenure_months",
    "churned",
)
SERVICE_FIELDS = (
    "phone_service",
    "multiple_lines",
    "internet_service",
    "online_security",
    "online_backup",
    "device_protection",
    "tech_support",
    "streaming_tv",
    "streaming_movies",
)
SOURCE = "ingestion-api"

UpsertStatus = Literal["created", "updated", "unchanged", "conflict"]


@dataclass
class UpsertResult:
    status: UpsertStatus
    server_version: int
    server_record: dict[str, Any] | None = None


@dataclass
class BatchOutcome:
    batch_id: str
    status: str
    accepted_count: int = 0
    rejected_count: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    replayed: bool = False

    @property
    def outcome(self) -> str:
        if self.accepted_count and not (self.rejected_count or self.conflicts):
            return "ACCEPTED"
        if self.accepted_count:
            return "PARTIAL"
        return "REJECTED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": self.status,
            "outcome": self.outcome,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "errors": self.errors,
            "conflicts": self.conflicts,
            "replayed": self.replayed,
        }


class BatchEnvelope(BaseModel):
    """Batch body; records stay untyped so every row can be validated and reported on its own."""

    model_config = ConfigDict(extra="forbid")

    batch_id: uuid.UUID
    client_id: str = Field(min_length=1, max_length=64)
    created_at: datetime
    source: Literal["form", "csv"] = "form"
    records: list[Any] = Field(min_length=1)


# --------------------------------------------------------------------------- helpers
def _months_before(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) - months, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _num(v: Decimal | float | None) -> float | None:
    return None if v is None else round(float(v), 2)


def record_from_db(customer: Customer) -> dict[str, Any] | None:
    """Full TelcoRecord dict for a customer, or None while the subscription is incomplete."""
    sub = customer.subscription
    if sub is None or sub.services is None:
        return None
    svc = sub.services
    return {
        "customer_id": customer.customer_id,
        "gender": customer.gender,
        "senior_citizen": int(customer.senior_citizen),
        "partner": customer.partner,
        "dependents": customer.dependents,
        "tenure_months": int(sub.tenure_months),
        **{f: getattr(svc, f) for f in SERVICE_FIELDS},
        "contract_type": sub.contract_type,
        "paperless_billing": sub.paperless_billing,
        "payment_method": sub.payment_method,
        "monthly_charges": _num(sub.monthly_charges),
        "total_charges": _num(sub.total_charges),
        "churned": bool(sub.churned),
        "version": int(customer.version),
    }


def customer_to_dict(c: Customer) -> dict[str, Any]:
    return {
        "customer_id": c.customer_id,
        "gender": c.gender,
        "senior_citizen": int(c.senior_citizen),
        "partner": c.partner,
        "dependents": c.dependents,
        "version": int(c.version),
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def subscription_to_dict(c: Customer) -> dict[str, Any] | None:
    sub = c.subscription
    if sub is None:
        return None
    out: dict[str, Any] = {
        "subscription_id": sub.subscription_id,
        "customer_id": c.customer_id,
        "contract_type": sub.contract_type,
        "paperless_billing": sub.paperless_billing,
        "payment_method": sub.payment_method,
        "monthly_charges": _num(sub.monthly_charges),
        "total_charges": _num(sub.total_charges),
        "tenure_months": sub.tenure_months,
        "start_date": sub.start_date.isoformat(),
        "end_date": sub.end_date.isoformat() if sub.end_date else None,
        "churned": bool(sub.churned),
        "churn_date": sub.churn_date.isoformat() if sub.churn_date else None,
        "version": int(c.version),
    }
    if sub.services is not None:
        out.update({f: getattr(sub.services, f) for f in SERVICE_FIELDS})
    return out


def _same(current: dict[str, Any] | None, incoming: dict[str, Any]) -> bool:
    if current is None:
        return False
    return all(current.get(f) == incoming.get(f) for f in RECORD_FIELDS)


def _enqueue(session: Session, topic: str, key: str, message: dict[str, Any]) -> None:
    session.add(
        EventOutbox(event_id=message["event_id"], batch_id=message.get("batch_id"), topic=topic, message_key=key, payload=message)
    )


def enqueue_record_event(session: Session, record: dict[str, Any], *, kind: str, batch_id: str | None) -> None:
    topic = TOPIC_CUSTOMERS if kind == "customer" else TOPIC_SUBSCRIPTIONS
    payload = {k: v for k, v in record.items() if k != "version"}
    msg = envelope(f"{kind}.upserted", payload, source=SOURCE, batch_id=batch_id)
    _enqueue(session, topic, record["customer_id"], msg)


def _audit(session: Session, actor: str, action: str, entity_id: str, before: Any, after: Any, batch_id: str | None) -> None:
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            entity="customer",
            entity_id=entity_id,
            batch_id=batch_id,
            before_json=before,
            after_json=after,
        )
    )


def _apply_subscription(c: Customer, values: dict[str, Any], today: date) -> None:
    sub = c.subscription
    tenure = int(values["tenure_months"])
    churned = bool(values["churned"])
    if sub is None:
        sub = Subscription(customer_id=c.customer_id, start_date=_months_before(today, tenure))
        c.subscription = sub
    was_churned = bool(sub.churned) if sub.churned is not None else False
    sub.contract_type = values["contract_type"]
    sub.paperless_billing = values["paperless_billing"]
    sub.payment_method = values["payment_method"]
    sub.monthly_charges = Decimal(str(values["monthly_charges"]))
    sub.total_charges = None if values["total_charges"] is None else Decimal(str(values["total_charges"]))
    if sub.tenure_months != tenure:
        sub.start_date = _months_before(today, tenure)
    sub.tenure_months = tenure
    sub.churned = churned
    if churned and not was_churned:
        sub.churn_date = sub.end_date = today
    elif not churned:
        sub.churn_date = sub.end_date = None
    if sub.services is None:
        sub.services = SubscriptionServices()
    for f in SERVICE_FIELDS:
        setattr(sub.services, f, values[f])


# --------------------------------------------------------------------------- record upsert
def upsert_record(session: Session, rec: TelcoRecord, *, actor: str, batch_id: str | None) -> UpsertResult:
    """Create or update one full record inside the caller's transaction.

    Optimistic locking: an update must carry the server version the client last
    saw. A stale version is returned as a conflict (server wins) and nothing is changed.
    """
    data = rec.payload()
    today = datetime.now(UTC).date()
    stmt = select(Customer).where(Customer.customer_id == rec.customer_id)
    if session.bind is not None and session.bind.dialect.name == "mysql":
        stmt = stmt.with_for_update()
    customer = session.execute(stmt).scalar_one_or_none()

    if customer is None:
        customer = Customer(customer_id=rec.customer_id, version=1, **{f: data[f] for f in CUSTOMER_FIELDS})
        session.add(customer)
        _apply_subscription(customer, data, today)
        session.flush()
        after = record_from_db(customer)
        _audit(session, actor, "create", rec.customer_id, None, after, batch_id)
        assert after is not None
        enqueue_record_event(session, after, kind="subscription", batch_id=batch_id)
        return UpsertResult("created", 1)

    before = record_from_db(customer)
    if _same(before, data):
        return UpsertResult("unchanged", int(customer.version))
    if rec.version != customer.version:
        return UpsertResult("conflict", int(customer.version), before)

    for f in CUSTOMER_FIELDS:
        setattr(customer, f, data[f])
    _apply_subscription(customer, data, today)
    customer.version = int(customer.version) + 1
    session.flush()
    after = record_from_db(customer)
    _audit(session, actor, "update", rec.customer_id, before, after, batch_id)
    assert after is not None
    customer_changed = before is None or any(before[f] != after[f] for f in CUSTOMER_FIELDS)
    enqueue_record_event(session, after, kind="customer" if customer_changed else "subscription", batch_id=batch_id)
    return UpsertResult("updated", int(customer.version))


# --------------------------------------------------------------------------- batches
def checksum(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def process_batch(
    factory: sessionmaker[Session],
    *,
    body: bytes,
    idempotency_key: str,
    checksum_header: str,
    actor: str,
    max_records: int,
    max_bytes: int,
) -> BatchOutcome:
    """Validate and apply one batch. Re-sending the same Idempotency-Key returns the original result."""
    if len(body) > max_bytes:
        raise ProblemError(413, "Payload Too Large", f"Batch payload exceeds {max_bytes} bytes")
    try:
        uuid.UUID(idempotency_key)
    except ValueError as exc:
        raise ProblemError(400, "Bad Request", "Idempotency-Key must be a UUID") from exc
    digest = checksum(body)
    if checksum_header.lower() != digest:
        raise ProblemError(
            400,
            "Bad Request",
            "X-Checksum-SHA256 does not match the request body",
            type_="https://telco.local/problems/checksum-mismatch",
        )

    with factory() as session:
        existing = session.execute(
            select(IngestionBatch).where(IngestionBatch.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing is not None:
            return _replay(existing, digest)

    try:
        parsed = BatchEnvelope.model_validate_json(body)
    except ValidationError as exc:
        raise ProblemError(
            422,
            "Unprocessable Content",
            "Batch envelope is invalid",
            type_="https://telco.local/problems/validation",
            errors=[{"field": ".".join(map(str, e["loc"])), "code": e["type"], "message": e["msg"]} for e in exc.errors()],
        ) from exc
    if len(parsed.records) > max_records:
        raise ProblemError(413, "Payload Too Large", f"A batch may contain at most {max_records} records")

    batch_id = str(parsed.batch_id)
    with factory() as session:
        batch = IngestionBatch(
            batch_id=batch_id,
            idempotency_key=idempotency_key,
            client_id=parsed.client_id,
            submitted_by=actor,
            source=parsed.source,
            record_count=len(parsed.records),
            status="RECEIVED",
            checksum_sha256=digest,
        )
        session.add(batch)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            # Same key raced in, or the batch_id was reused under another key.
            existing = session.execute(
                select(IngestionBatch).where(IngestionBatch.idempotency_key == idempotency_key)
            ).scalar_one_or_none()
            if existing is not None:
                return _replay(existing, digest)
            raise ProblemError(409, "Conflict", "batch_id already used with a different Idempotency-Key") from exc

    outcome = BatchOutcome(batch_id=batch_id, status="RECEIVED")
    row_errors: list[RowError] = []
    with factory() as session:
        try:
            batch = session.get(IngestionBatch, batch_id)
            assert batch is not None
            seen: set[str] = set()
            for row, raw in enumerate(parsed.records):
                rec, errors = validate_record(raw, row)
                if rec is not None and rec.customer_id in seen:
                    errors = [
                        RowError(row, "customer_id", "duplicate_in_batch", "customer_id appears more than once in this batch")
                    ]
                    rec = None
                if rec is None:
                    row_errors.extend(errors)
                    _enqueue(
                        session,
                        TOPIC_DLQ,
                        str(raw.get("customer_id", "unknown")) if isinstance(raw, dict) else "unknown",
                        envelope(
                            "record.rejected",
                            {"row": row, "record": raw, "errors": [e.as_dict() for e in errors]},
                            source=SOURCE,
                            batch_id=batch_id,
                        ),
                    )
                    continue
                seen.add(rec.customer_id)
                with session.begin_nested():
                    result = upsert_record(session, rec, actor=actor, batch_id=batch_id)
                if result.status == "conflict":
                    outcome.conflicts.append(
                        {
                            "row": row,
                            "customer_id": rec.customer_id,
                            "server_version": result.server_version,
                            "client_version": rec.version,
                            "server_record": result.server_record,
                        }
                    )
                else:
                    outcome.accepted_count += 1
            outcome.errors = [e.as_dict() for e in row_errors]
            outcome.rejected_count = len({e.row for e in row_errors})
            for e in row_errors:
                session.add(
                    IngestionError(
                        batch_id=batch_id, row_number=e.row, field=e.field[:64], error_code=e.code[:64], message=e.message
                    )
                )
            outcome.status = "VALIDATED"
            batch.accepted_count = outcome.accepted_count
            batch.rejected_count = outcome.rejected_count
            batch.conflict_count = len(outcome.conflicts)
            batch.status = outcome.status
            batch.processed_at = datetime.now(UTC).replace(tzinfo=None)
            batch.result_json = outcome.as_dict()
            session.commit()
        except Exception:
            session.rollback()
            log.exception("batch processing failed", extra={"batch_id": batch_id})
            with factory() as s2:
                b = s2.get(IngestionBatch, batch_id)
                if b is not None:
                    b.status = "FAILED"
                    b.processed_at = datetime.now(UTC).replace(tzinfo=None)
                    b.result_json = {
                        **BatchOutcome(batch_id=batch_id, status="FAILED").as_dict(),
                        "errors": [
                            {
                                "row": 0,
                                "field": "",
                                "code": "internal_error",
                                "message": "The batch could not be processed; resend it later",
                            }
                        ],
                    }
                    s2.commit()
            raise
    log.info(
        "batch processed",
        extra={
            "batch_id": batch_id,
            "accepted": outcome.accepted_count,
            "rejected": outcome.rejected_count,
            "conflicts": len(outcome.conflicts),
        },
    )
    return outcome


def replay_if_known(factory: sessionmaker[Session], idempotency_key: str) -> BatchOutcome | None:
    """Stored result for a key, or None. Used by CSV upload, where the batch id is
    derived from the file hash so the payload digest is not needed to match."""
    with factory() as session:
        batch = session.execute(
            select(IngestionBatch).where(IngestionBatch.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        return None if batch is None else _replay(batch, batch.checksum_sha256)


def _replay(batch: IngestionBatch, digest: str) -> BatchOutcome:
    if batch.checksum_sha256 != digest:
        raise ProblemError(
            422,
            "Unprocessable Content",
            "This Idempotency-Key was already used for a different payload",
            type_="https://telco.local/problems/idempotency-key-reuse",
        )
    if batch.result_json is None:
        raise ProblemError(409, "Conflict", "This batch is still being processed; retry shortly", headers={"Retry-After": "2"})
    data = dict(batch.result_json)
    data["status"] = batch.status
    out = BatchOutcome(
        batch_id=data["batch_id"],
        status=data["status"],
        accepted_count=data["accepted_count"],
        rejected_count=data["rejected_count"],
        errors=data["errors"],
        conflicts=data["conflicts"],
        replayed=True,
    )
    return out


def batch_payload_bytes(batch_id: str, client_id: str, records: list[dict[str, Any]], source: str) -> bytes:
    """Serialise a server-built batch (CSV upload) exactly like the PWA does."""
    return json.dumps(
        {
            "batch_id": batch_id,
            "client_id": client_id,
            "created_at": datetime.now(UTC).isoformat(),
            "source": source,
            "records": records,
        },
        separators=(",", ":"),
    ).encode()
