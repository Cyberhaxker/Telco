"""/healthz (liveness) and /readyz (readiness with dependency checks)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

ReadinessCheck = Callable[[], Awaitable[None]]


def health_router(checks: dict[str, ReadinessCheck] | None = None) -> APIRouter:
    router = APIRouter(tags=["health"])
    checks = checks or {}

    @router.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        results: dict[str, str] = {}
        ok = True
        for name, check in checks.items():
            try:
                await asyncio.wait_for(check(), timeout=3)
                results[name] = "ok"
            except Exception as exc:  # noqa: BLE001 - report any failure
                ok = False
                results[name] = f"fail: {type(exc).__name__}"
        return JSONResponse({"status": "ok" if ok else "degraded", "checks": results}, status_code=200 if ok else 503)

    return router
