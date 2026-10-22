"""Pure message handling: decode, validate and turn Kafka messages into rows."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from telco_common.kafka import TOPIC_CUSTOMERS, TOPIC_DLQ, TOPIC_SUBSCRIPTIONS
from telco_common.records import validate_record

INGEST_TOPICS = (TOPIC_CUSTOMERS, TOPIC_SUBSCRIPTIONS)
EXPECTED_EVENTS = {TOPIC_CUSTOMERS: "customer.upserted", TOPIC_SUBSCRIPTIONS: "subscription.upserted"}


@dataclass(frozen=True)
class EventRow:
    event_id: str
    event_type: str
    schema_version: str
    batch_id: str | None
    customer_id: str
    produced_at: datetime
    source: str
    payload: dict[str, Any]
    topic: str
    partition: int
    offset: int


@dataclass(frozen=True)
class DlqRow:
    event_id: str | None
    topic: str
    partition: int
    offset: int
    error_code: str
    error_message: str
    raw_value: str


def _uuid_or_none(v: Any) -> str | None:
    try:
        return str(uuid.UUID(str(v)))
    except (ValueError, TypeError):
        return None


def handle(topic: str, partition: int, offset: int, value: bytes | None) -> EventRow | DlqRow:
    raw = (value or b"").decode("utf-8", errors="replace")

    def dlq(code: str, msg: str, event_id: str | None = None) -> DlqRow:
        return DlqRow(event_id, topic, partition, offset, code, msg, raw[:100_000])

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as exc:
        return dlq("invalid_json", str(exc))
    if not isinstance(msg, dict):
        return dlq("invalid_envelope", "message is not a JSON object")
    event_id = _uuid_or_none(msg.get("event_id"))

    if topic == TOPIC_DLQ:
        # Records rejected by ingestion-api: keep them in the warehouse for stewards.
        errors = msg.get("payload", {}).get("errors", [])
        return dlq("rejected_at_ingestion", json.dumps(errors)[:4000], event_id)

    missing = [k for k in ("event_id", "event_type", "schema_version", "produced_at", "source", "payload") if k not in msg]
    if missing or event_id is None:
        return dlq("invalid_envelope", f"missing or invalid fields: {', '.join(missing) or 'event_id'}", event_id)
    if msg["event_type"] != EXPECTED_EVENTS.get(topic):
        return dlq("unexpected_event_type", f"{msg['event_type']} is not valid on {topic}", event_id)
    if str(msg["schema_version"]) != "1":
        return dlq("unsupported_schema_version", f"schema_version {msg['schema_version']}", event_id)
    try:
        produced_at = datetime.fromisoformat(str(msg["produced_at"]).replace("Z", "+00:00"))
    except ValueError:
        return dlq("invalid_envelope", "produced_at is not ISO-8601", event_id)

    record, errors = validate_record(msg["payload"], 0)
    if record is None:
        return dlq("invalid_record", "; ".join(f"{e.field}: {e.message}" for e in errors)[:4000], event_id)

    return EventRow(
        event_id=event_id,
        event_type=msg["event_type"],
        schema_version=str(msg["schema_version"]),
        batch_id=_uuid_or_none(msg.get("batch_id")),
        customer_id=record.customer_id,
        produced_at=produced_at,
        source=str(msg["source"]),
        payload=record.payload(),
        topic=topic,
        partition=partition,
        offset=offset,
    )
