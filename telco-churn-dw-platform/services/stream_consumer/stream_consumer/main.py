"""Kafka -> PostgreSQL raw consumer (at-least-once, idempotent upsert on event_id).

Offsets are committed only after the batch is durably written, so a crash
replays messages, and the event_id / (topic, partition, offset) uniqueness
makes the replay harmless.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import signal
import time

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from psycopg import AsyncConnection, OperationalError
from telco_common.kafka import TOPIC_CUSTOMERS, TOPIC_DLQ, TOPIC_SUBSCRIPTIONS
from telco_common.logging import configure_logging

from .handlers import DlqRow, EventRow, handle
from .sink import write

log = logging.getLogger("stream_consumer")

MESSAGES = Counter("stream_consumer_messages_total", "Messages processed", ["topic", "result"])
BATCH_SECONDS = Histogram("stream_consumer_batch_seconds", "Time to write one batch")
LAST_SUCCESS = Gauge("stream_consumer_last_success_timestamp", "Unix time of the last committed batch")
RETRIES = Counter("stream_consumer_write_retries_total", "Database write retries")


class State:
    def __init__(self) -> None:
        self.started = time.time()
        self.last_poll = 0.0
        self.healthy = False


async def serve_health(state: State, port: int) -> asyncio.base_events.Server:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = (await reader.readline()).decode(errors="replace")
            path = line.split(" ")[1] if " " in line else "/"
            while (await reader.readline()) not in (b"\r\n", b"\n", b""):
                pass
            if path.startswith("/metrics"):
                body, ctype, status = generate_latest(), CONTENT_TYPE_LATEST, "200 OK"
            else:
                ok = state.healthy and time.time() - state.last_poll < 60
                body = b'{"status":"ok"}' if ok else b'{"status":"unhealthy"}'
                ctype, status = "application/json", "200 OK" if ok else "503 Service Unavailable"
            writer.write(
                f"HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                + body
            )
            await writer.drain()
        finally:
            writer.close()

    return await asyncio.start_server(handler, "0.0.0.0", port)  # noqa: S104 - container-internal health/metrics port


async def connect_db(dsn: str) -> AsyncConnection:
    delay = 1.0
    while True:
        try:
            return await AsyncConnection.connect(dsn, application_name="stream-consumer")
        except OperationalError as exc:
            log.warning("database not reachable (%s); retrying in %.0fs", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)


async def write_with_retry(dsn: str, conn: AsyncConnection, rows: list[EventRow | DlqRow]) -> AsyncConnection:
    """Retry with exponential backoff + jitter; never drop a batch."""
    attempt = 0
    while True:
        try:
            with BATCH_SECONDS.time():
                await write(conn, rows)
            return conn
        except OperationalError as exc:
            attempt += 1
            RETRIES.inc()
            delay = min(2**attempt, 60) * (0.5 + random.random())
            log.warning("write failed (%s); retry %d in %.1fs", exc, attempt, delay)
            await asyncio.sleep(delay)
            if conn.closed or conn.broken:
                conn = await connect_db(dsn)


async def run() -> None:
    configure_logging(os.environ.get("SERVICE_NAME", "stream-consumer"), os.environ.get("LOG_LEVEL", "INFO"))
    dsn = os.environ["DW_DSN"]
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    group = os.environ.get("KAFKA_GROUP_ID", "dw-stream-consumer")
    state = State()
    health = await serve_health(state, int(os.environ.get("HEALTH_PORT", "8001")))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    conn = await connect_db(dsn)
    consumer = AIOKafkaConsumer(
        TOPIC_CUSTOMERS,
        TOPIC_SUBSCRIPTIONS,
        TOPIC_DLQ,
        bootstrap_servers=bootstrap,
        group_id=group,
        client_id="stream-consumer",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        isolation_level="read_committed",
        max_poll_records=500,
    )
    while not stop.is_set():
        try:
            await consumer.start()
            break
        except KafkaError as exc:
            log.warning("kafka not reachable (%s); retrying", exc)
            await asyncio.sleep(3)
    state.healthy = True
    log.info("consuming", extra={"group": group})
    try:
        while not stop.is_set():
            batches = await consumer.getmany(timeout_ms=1000, max_records=500)
            state.last_poll = time.time()
            if not batches:
                continue
            rows: list[EventRow | DlqRow] = []
            for tp, messages in batches.items():
                for m in messages:
                    row = handle(tp.topic, tp.partition, m.offset, m.value)
                    rows.append(row)
                    MESSAGES.labels(tp.topic, "event" if isinstance(row, EventRow) else row.error_code).inc()
            conn = await write_with_retry(dsn, conn, rows)
            await consumer.commit()
            LAST_SUCCESS.set_to_current_time()
            log.info("batch committed", extra={"messages": len(rows)})
    finally:
        state.healthy = False
        await consumer.stop()
        await conn.close()
        health.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
