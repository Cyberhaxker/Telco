from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from telco_common.app import create_app

from .config import Settings, get_settings
from .lineage import Lineage
from .routers import meta


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    pool = AsyncConnectionPool(
        settings.dw_dsn, min_size=1, max_size=8, open=False, kwargs={"application_name": "metadata-api", "autocommit": True}
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await pool.open(wait=False)
        yield
        await pool.close()

    async def db_ready() -> None:
        async with pool.connection(timeout=3) as conn:
            await conn.execute("select 1")

    app = create_app(
        settings,
        title="Telco Metadata API",
        description="Dataset registry, data dictionary, dbt lineage, data-quality results and pipeline status.",
        api_prefix="/api/v1/meta",
        lifespan=lifespan,
        readiness={"warehouse": db_ready},
    )
    app.state.pool = pool
    app.state.lineage = Lineage(Path(settings.dbt_manifest_path))
    app.state.member_cache = {}
    app.include_router(meta.router)
    return app
