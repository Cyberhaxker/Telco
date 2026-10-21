"""Structured JSON logging with request-id propagation."""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_ctx: ContextVar[str | None] = ContextVar("user", default=None)

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if rid := request_id_ctx.get():
            out["request_id"] = rid
        if user := user_ctx.get():
            out["user"] = user
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                out[key] = value
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure_logging(service: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).handlers[:] = []
        logging.getLogger(noisy).propagate = False
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Reads/creates X-Request-ID (set by APISIX) and logs one line per request."""

    def __init__(self, app, logger_name: str = "access") -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.log = logging.getLogger(logger_name)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        token = request_id_ctx.set(rid)
        user_token = user_ctx.set(None)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            if request.url.path not in ("/healthz", "/readyz", "/metrics"):
                self.log.info(
                    "request",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status": status,
                        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                    },
                )
            request_id_ctx.reset(token)
            user_ctx.reset(user_token)
