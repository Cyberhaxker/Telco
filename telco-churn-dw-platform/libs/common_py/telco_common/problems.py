"""RFC 9457 problem+json error responses for every service."""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .logging import request_id_ctx

PROBLEM_JSON = "application/problem+json"
log = logging.getLogger(__name__)


class ProblemError(Exception):
    """Raise anywhere to return a problem+json response."""

    def __init__(
        self,
        status: int,
        title: str | None = None,
        detail: str | None = None,
        type_: str = "about:blank",
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(detail or title)
        self.headers = headers
        self.status = status
        self.title = title or HTTPStatus(status).phrase
        self.detail = detail
        self.type = type_
        self.extra = extra


def problem_response(
    request: Request,
    status: int,
    title: str,
    detail: str | None = None,
    type_: str = "about:blank",
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    body: dict[str, Any] = {"type": type_, "title": title, "status": status, "instance": request.url.path}
    if detail:
        body["detail"] = detail
    if rid := request_id_ctx.get():
        body["request_id"] = rid
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(request, exc.status, exc.title, exc.detail, exc.type, exc.headers, **exc.extra)

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else None
        extra = {} if isinstance(exc.detail, str) or exc.detail is None else {"errors": exc.detail}
        return problem_response(
            request, exc.status_code, HTTPStatus(exc.status_code).phrase, detail, headers=exc.headers, **extra
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", ()) if p != "body"), "code": e.get("type"), "message": e.get("msg")}
            for e in exc.errors()
        ]
        return problem_response(
            request,
            422,
            "Unprocessable Content",
            "Request validation failed",
            type_="https://telco.local/problems/validation",
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", extra={"path": request.url.path})
        return problem_response(request, 500, "Internal Server Error", "An unexpected error occurred")
