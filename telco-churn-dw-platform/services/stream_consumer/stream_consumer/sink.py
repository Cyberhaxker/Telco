"""Idempotent writes into raw.ingest_events / raw.ingest_dlq."""

from __future__ import annotations

from collections.abc import Sequence

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from .handlers import DlqRow, EventRow

INSERT_EVENT = """
INSERT INTO raw.ingest_events
    (event_id, event_type, schema_version, batch_id, customer_id, produced_at, source, payload,
     kafka_topic, kafka_partition, kafka_offset, _source)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'kafka:' || %s)
ON CONFLICT (event_id) DO NOTHING
"""

INSERT_DLQ = """
INSERT INTO raw.ingest_dlq (event_id, kafka_topic, kafka_partition, kafka_offset, error_code, error_message, raw_value)
SELECT %s, %s, %s, %s, %s, %s, %s
WHERE NOT EXISTS (
    SELECT 1 FROM raw.ingest_dlq WHERE kafka_topic = %s AND kafka_partition = %s AND kafka_offset = %s
)
"""


async def write(conn: AsyncConnection, rows: Sequence[EventRow | DlqRow]) -> tuple[int, int]:
    events = [r for r in rows if isinstance(r, EventRow)]
    dlq = [r for r in rows if isinstance(r, DlqRow)]
    async with conn.transaction(), conn.cursor() as cur:
        if events:
            await cur.executemany(
                INSERT_EVENT,
                [
                    (
                        e.event_id,
                        e.event_type,
                        e.schema_version,
                        e.batch_id,
                        e.customer_id,
                        e.produced_at,
                        e.source,
                        Jsonb(e.payload),
                        e.topic,
                        e.partition,
                        e.offset,
                        e.topic,
                    )
                    for e in events
                ],
            )
        if dlq:
            await cur.executemany(
                INSERT_DLQ,
                [
                    (
                        d.event_id,
                        d.topic,
                        d.partition,
                        d.offset,
                        d.error_code,
                        d.error_message,
                        d.raw_value,
                        d.topic,
                        d.partition,
                        d.offset,
                    )
                    for d in dlq
                ],
            )
    return len(events), len(dlq)
