from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from telco_common.app import create_app

from .config import Settings, get_settings
from .db import make_engine, make_session_factory, ping
from .outbox import KafkaPublisher, OutboxRelay, Publisher
from .routers import batches, records

log = logging.getLogger(__name__)


def build_app(settings: Settings | None = None, publisher: Publisher | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = make_engine(settings.ops_database_url)
    factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        relay = None
        if settings.kafka_enabled:
            pub = publisher or KafkaPublisher(settings.kafka_bootstrap_servers)
            relay = OutboxRelay(factory, pub, settings.outbox_poll_seconds, settings.outbox_batch_size)
            relay.start()
        app.state.relay = relay
        yield
        if relay is not None:
            relay.stop()
            relay.join(timeout=15)
        engine.dispose()

    async def db_ready() -> None:
        await asyncio.to_thread(ping, engine)

    app = create_app(
        settings,
        title="Telco Ingestion API",
        description="Data entry, idempotent batch ingestion with per-row validation, and Kafka publishing.",
        api_prefix="/api/v1/ingest",
        lifespan=lifespan,
        readiness={"mysql": db_ready},
    )
    app.state.engine = engine
    app.state.session_factory = factory
    app.include_router(records.router)
    app.include_router(batches.router)
    return app
