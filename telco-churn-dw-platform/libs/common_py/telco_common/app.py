"""FastAPI application factory with the platform's cross-cutting concerns."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .auth import TokenVerifier
from .health import ReadinessCheck, health_router
from .logging import RequestContextMiddleware, configure_logging
from .problems import install_problem_handlers
from .settings import ServiceSettings

Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]] | Callable[[FastAPI], AsyncIterator[None]]


def create_app(
    settings: ServiceSettings,
    *,
    title: str,
    api_prefix: str,
    description: str = "",
    version: str = "1.0.0",
    lifespan: Lifespan | None = None,
    readiness: dict[str, ReadinessCheck] | None = None,
) -> FastAPI:
    configure_logging(settings.service_name, settings.log_level)
    if settings.auth_disabled and settings.is_production:
        raise RuntimeError("AUTH_DISABLED cannot be used in production")

    app = FastAPI(
        title=title,
        description=description,
        version=version,
        lifespan=lifespan,  # type: ignore[arg-type]
        docs_url=f"{api_prefix}/docs",
        redoc_url=None,
        openapi_url=f"{api_prefix}/openapi.json",
        swagger_ui_init_oauth=None,
    )
    app.state.settings = settings
    app.state.token_verifier = TokenVerifier(settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID", "X-Checksum-SHA256", "If-Match"],
        expose_headers=["X-Request-ID", "ETag"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)
    install_problem_handlers(app)
    app.include_router(health_router(readiness))

    Instrumentator(
        excluded_handlers=["/healthz", "/readyz", "/metrics"],
        should_group_status_codes=False,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    @app.middleware("http")
    async def security_headers(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    return app
