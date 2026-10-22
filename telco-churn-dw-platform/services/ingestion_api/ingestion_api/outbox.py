"""Relays rows from event_outbox to Kafka (acks=all, idempotent producer).

Events are written in the same MySQL transaction as the data change, so a
Kafka outage delays events but never loses them or lets MySQL and Kafka disagree.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker
from telco_common.kafka import encode

from .models import EventOutbox, IngestionBatch

log = logging.getLogger(__name__)


class Publisher(Protocol):
    def publish(self, messages: list[tuple[str, str, bytes, str]]) -> dict[str, str | None]:
        """Send (topic, key, value, event_id) tuples; return {event_id: error or None}."""

    def close(self) -> None: ...


class KafkaPublisher:
    def __init__(self, bootstrap_servers: str, client_id: str = "ingestion-api") -> None:
        from confluent_kafka import Producer

        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "client.id": client_id,
                "acks": "all",
                "enable.idempotence": True,
                "compression.type": "lz4",
                "linger.ms": 20,
                "message.timeout.ms": 30000,
            }
        )

    def publish(self, messages: list[tuple[str, str, bytes, str]]) -> dict[str, str | None]:
        results: dict[str, str | None] = {}

        def on_delivery(err, msg, event_id):  # type: ignore[no-untyped-def]
            results[event_id] = None if err is None else str(err)

        for topic, key, value, event_id in messages:
            self._producer.produce(
                topic,
                key=key.encode(),
                value=value,
                headers={"event_id": event_id},
                on_delivery=lambda err, msg, eid=event_id: on_delivery(err, msg, eid),
            )
            self._producer.poll(0)
        remaining = self._producer.flush(30)
        for _, _, _, event_id in messages:
            results.setdefault(event_id, "delivery timed out" if remaining else None)
        return results

    def close(self) -> None:
        self._producer.flush(10)


def relay_once(factory: sessionmaker[Session], publisher: Publisher, batch_size: int = 500) -> int:
    """Publish one page of pending events. Returns the number published."""
    with factory() as session:
        stmt = select(EventOutbox).where(EventOutbox.published_at.is_(None)).order_by(EventOutbox.id).limit(batch_size)
        if session.bind is not None and session.bind.dialect.name == "mysql":
            stmt = stmt.with_for_update(skip_locked=True)
        rows = list(session.execute(stmt).scalars())
        if not rows:
            session.rollback()
            return 0
        results = publisher.publish([(r.topic, r.message_key, encode(r.payload), r.event_id) for r in rows])
        now = datetime.now(UTC).replace(tzinfo=None)
        published = 0
        batch_ids: set[str] = set()
        for r in rows:
            err = results.get(r.event_id, "no delivery report")
            r.attempts += 1
            if err is None:
                r.published_at = now
                r.last_error = None
                published += 1
                if r.batch_id:
                    batch_ids.add(r.batch_id)
            else:
                r.last_error = err[:2000]
        session.flush()
        for bid in batch_ids:
            pending = session.scalar(
                select(func.count())
                .select_from(EventOutbox)
                .where(EventOutbox.batch_id == bid, EventOutbox.published_at.is_(None))
            )
            if not pending:
                session.execute(
                    update(IngestionBatch)
                    .where(IngestionBatch.batch_id == bid, IngestionBatch.status == "VALIDATED")
                    .values(status="PUBLISHED")
                )
        session.commit()
        if published < len(rows):
            log.warning("outbox relay: %d of %d events failed", len(rows) - published, len(rows))
        return published


class OutboxRelay(threading.Thread):
    def __init__(self, factory: sessionmaker[Session], publisher: Publisher, poll_seconds: float, batch_size: int) -> None:
        super().__init__(name="outbox-relay", daemon=True)
        self.factory = factory
        self.publisher = publisher
        self.poll_seconds = poll_seconds
        self.batch_size = batch_size
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.last_error: str | None = None

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def run(self) -> None:
        backoff = self.poll_seconds
        while not self._stop.is_set():
            try:
                n = relay_once(self.factory, self.publisher, self.batch_size)
                self.last_error = None
                backoff = self.poll_seconds
                if n == self.batch_size:
                    continue  # more pending: drain immediately
            except Exception as exc:  # noqa: BLE001 - keep relaying after transient failures
                self.last_error = str(exc)
                log.exception("outbox relay error")
                backoff = min(backoff * 2, 30.0)
            self._wake.wait(backoff)
            self._wake.clear()
        self.publisher.close()
