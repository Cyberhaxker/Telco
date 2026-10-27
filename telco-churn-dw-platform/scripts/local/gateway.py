"""Minimal stand-in for APISIX when running without Docker.

Routes /api/v1/{ingest,meta,analytics}/* to the local services (same paths the
real gateway uses), adds CORS, and streams responses so SSE works.
Run: python scripts/local/gateway.py   (listens on :9080)
"""

from __future__ import annotations

import os

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

UPSTREAMS = {
    "ingest": os.environ.get("INGEST_URL", "http://127.0.0.1:8001"),
    "meta": os.environ.get("META_URL", "http://127.0.0.1:8002"),
    "analytics": os.environ.get("ANALYTICS_URL", "http://127.0.0.1:8003"),
}
HOP = {"host", "content-length", "connection", "transfer-encoding", "keep-alive", "content-encoding"}

app = FastAPI(title="Local gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag", "Retry-After"],
)
client = httpx.AsyncClient(timeout=httpx.Timeout(30, read=None))


@app.get("/")
@app.get("/api/v1")
@app.get("/api/v1/")
async def index() -> dict[str, object]:
    return {
        "name": "Telco churn DW local gateway",
        "services": {name: f"/api/v1/{name}/" for name in UPSTREAMS},
        "examples": ["/api/v1/analytics/charts", "/api/v1/analytics/stream", "/api/v1/meta/datasets"],
    }


@app.api_route("/api/v1/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(service: str, path: str, request: Request):  # type: ignore[no-untyped-def]
    base = UPSTREAMS.get(service)
    if base is None:
        return JSONResponse({"title": "Not Found", "status": 404, "detail": f"unknown service {service}"}, status_code=404)
    url = f"{base}/api/v1/{service}/{path}"
    req = client.build_request(
        request.method,
        url,
        params=request.query_params,
        headers={k: v for k, v in request.headers.items() if k.lower() not in HOP},
        content=await request.body(),
    )
    try:
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        return JSONResponse({"title": "Bad Gateway", "status": 502, "detail": str(exc)}, status_code=502)
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k.lower() not in HOP},
        background=None,
        media_type=None,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("GATEWAY_PORT", "9080")))
