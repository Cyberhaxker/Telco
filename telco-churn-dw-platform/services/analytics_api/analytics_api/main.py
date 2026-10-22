from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from telco_common.app import create_app

from .config import Settings, get_settings
from .deps import Cache
from .model_service import ModelService
from .routers import analytics


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    pool = AsyncConnectionPool(
        settings.dw_dsn, min_size=1, max_size=10, open=False, kwargs={"application_name": "analytics-api", "autocommit": True}
    )
    cache = Cache(settings.valkey_url, settings.cache_ttl_seconds)
    models = ModelService(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await pool.open(wait=False)
        stop = asyncio.Event()
        # Never block start-up on MLflow: load in the background, retry while missing.
        tasks = [asyncio.create_task(models.keep_loaded(stop)), asyncio.create_task(models.listen_for_promotions(stop))]
        yield
        stop.set()
        for t in tasks:
            t.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await t
        await pool.close()
        await cache.close()

    async def db_ready() -> None:
        async with pool.connection(timeout=3) as conn:
            await conn.execute("select 1")

    app = create_app(
        settings,
        title="Telco Analytics API",
        description="OLAP (roll-up, drill-down, slice, dice, pivot), KPIs, churn predictions and model registry.",
        api_prefix="/api/v1/analytics",
        lifespan=lifespan,
        readiness={"warehouse": db_ready},
    )
    app.state.pool = pool
    app.state.cache = cache
    app.state.models = models
    app.include_router(analytics.router)
    return app
