from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from psycopg_pool import AsyncConnectionPool

from .config import Settings
from .model_service import ModelService

log = logging.getLogger(__name__)


def get_pool(request: Request) -> AsyncConnectionPool:
    return request.app.state.pool  # type: ignore[no-any-return]


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_models(request: Request) -> ModelService:
    return request.app.state.models  # type: ignore[no-any-return]


class Cache:
    """Thin Valkey cache; every failure degrades to a cache miss."""

    def __init__(self, url: str | None, ttl: int) -> None:
        self.ttl = ttl
        self._client = None
        if url:
            import redis.asyncio as redis

            self._client = redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)

    async def get_or_set(self, key: str, producer: Callable[[], Awaitable[Any]]) -> tuple[Any, bool]:
        if self._client is not None:
            try:
                hit = await self._client.get(key)
                if hit is not None:
                    return json.loads(hit), True
            except Exception as exc:  # noqa: BLE001
                log.warning("cache read failed: %s", exc)
        value = await producer()
        if self._client is not None:
            try:
                await self._client.set(key, json.dumps(value, default=str), ex=self.ttl)
            except Exception as exc:  # noqa: BLE001
                log.warning("cache write failed: %s", exc)
        return value, False

    async def ping(self) -> None:
        if self._client is not None:
            await self._client.ping()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()


def get_cache(request: Request) -> Cache:
    return request.app.state.cache  # type: ignore[no-any-return]


PoolDep = Annotated[AsyncConnectionPool, Depends(get_pool)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ModelsDep = Annotated[ModelService, Depends(get_models)]
CacheDep = Annotated[Cache, Depends(get_cache)]


async def fetch(pool: AsyncConnectionPool, query: Any, params: Any = None) -> tuple[list[str], list[tuple[Any, ...]]]:
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(query, params)
        cols = [d.name for d in cur.description] if cur.description else []
        return cols, await cur.fetchall()


def to_json_value(v: Any) -> Any:
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v
