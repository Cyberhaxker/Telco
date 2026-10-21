"""Kafka message envelope shared by producers and consumers."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

TOPIC_CUSTOMERS = "ingest.customers.v1"
TOPIC_SUBSCRIPTIONS = "ingest.subscriptions.v1"
TOPIC_DLQ = "ingest.dlq.v1"
TOPIC_DW_EVENTS = "dw.events.v1"


def envelope(
    event_type: str,
    payload: dict[str, Any],
    *,
    source: str,
    batch_id: str | None = None,
    schema_version: str = "1",
    event_id: str | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id or str(uuid.uuid4()),
        "event_type": event_type,
        "schema_version": schema_version,
        "batch_id": batch_id,
        "produced_at": datetime.now(UTC).isoformat(),
        "source": source,
        "payload": payload,
    }


def encode(message: dict[str, Any]) -> bytes:
    return json.dumps(message, separators=(",", ":"), default=str).encode()
