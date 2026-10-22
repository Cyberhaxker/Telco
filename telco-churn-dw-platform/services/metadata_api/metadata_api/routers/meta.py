from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field
from telco_common.auth import Principal, require_roles
from telco_common.pagination import Page, PageParams, page_params
from telco_common.problems import ProblemError

from ..config import Settings
from ..lineage import Lineage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/meta", tags=["metadata"])

Viewer = Annotated[Principal, Depends(require_roles("viewer", "data_entry", "analyst", "data_steward"))]
Steward = Annotated[Principal, Depends(require_roles("data_steward"))]
Operator = Annotated[Principal, Depends(require_roles("data_steward"))]

# Dimension members exposed to forms and filters: name -> (table, column). Whitelisted.
DIMENSIONS: dict[str, tuple[str, str]] = {
    "contract_type": ("marts.dim_contract", "contract_type"),
    "paperless_billing": ("marts.dim_contract", "paperless_billing"),
    "payment_method": ("marts.dim_payment", "payment_method"),
    "internet_service": ("marts.dim_service", "internet_service"),
    "phone_service": ("marts.dim_service", "phone_service"),
    "multiple_lines": ("marts.dim_service", "multiple_lines"),
    "online_security": ("marts.dim_service", "online_security"),
    "online_backup": ("marts.dim_service", "online_backup"),
    "device_protection": ("marts.dim_service", "device_protection"),
    "tech_support": ("marts.dim_service", "tech_support"),
    "streaming_tv": ("marts.dim_service", "streaming_tv"),
    "streaming_movies": ("marts.dim_service", "streaming_movies"),
    "tenure_band": ("marts.dim_tenure_band", "band_label"),
    "churn_label": ("marts.dim_churn", "churn_label"),
}
DAGS = ("seed_initial_csv", "ops_to_dw_daily", "ml_train_weekly", "ml_score_daily")


def pool_of(request: Request) -> AsyncConnectionPool:
    return request.app.state.pool  # type: ignore[no-any-return]


PoolDep = Annotated[AsyncConnectionPool, Depends(pool_of)]


async def rows(pool: AsyncConnectionPool, query: str, params: Any = None) -> list[dict[str, Any]]:
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(query, params)  # type: ignore[arg-type]
        cols = [d.name for d in cur.description or []]
        return [{c: _json(v) for c, v in zip(cols, r, strict=True)} for r in await cur.fetchall()]


def _json(v: Any) -> Any:
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID

    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


# ------------------------------------------------------------------ datasets
@router.get("/datasets", response_model=Page[dict[str, Any]])
async def datasets(
    _: Viewer,
    pool: PoolDep,
    page: Annotated[PageParams, Depends(page_params)],
    layer: Annotated[str | None, Query(max_length=20)] = None,
) -> Page[dict[str, Any]]:
    where, params = ("where layer = %s", [layer]) if layer else ("", [])
    total = (await rows(pool, f"select count(*) as n from meta.datasets {where}", params))[0]["n"]
    items = await rows(
        pool,
        f"select * from meta.datasets {where} order by layer, dataset_id limit %s offset %s",
        [*params, page.limit, page.offset],
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


# ------------------------------------------------------------------ dictionary
@router.get("/dictionary")
async def dictionary(
    request: Request,
    response: Response,
    _: Viewer,
    pool: PoolDep,
    table: Annotated[str | None, Query(max_length=64, description="table name, optionally schema-qualified")] = None,
    search: Annotated[str | None, Query(max_length=64)] = None,
) -> Any:
    where, params = ["true"], []
    if table:
        schema, _, name = table.rpartition(".")
        where.append("table_name = %s")
        params.append(name)
        if schema:
            where.append("schema_name = %s")
            params.append(schema)
    if search:
        where.append("(column_name ilike %s or business_name ilike %s or description ilike %s)")
        params += [f"%{search}%"] * 3
    items = await rows(
        pool,
        f"select * from meta.data_dictionary where {' and '.join(where)} order by schema_name, table_name, column_id",
        params,
    )
    etag = '"' + hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()[:32] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return {"items": items, "total": len(items)}


class DictionaryUpdate(BaseModel):
    business_name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_pii: bool
    is_protected_attribute: bool
    allowed_values: list[str] | None = Field(default=None, max_length=100)
    example_value: str | None = Field(default=None, max_length=200)
    version: int = Field(ge=1)


@router.put("/dictionary/{column_id}")
async def update_dictionary(column_id: int, body: DictionaryUpdate, principal: Steward, pool: PoolDep) -> dict[str, Any]:
    async with pool.connection() as conn, conn.transaction(), conn.cursor() as cur:
        await cur.execute("select * from meta.data_dictionary where column_id = %s for update", (column_id,))
        row = await cur.fetchone()
        if row is None:
            raise ProblemError(404, "Not Found", f"Dictionary entry {column_id} does not exist")
        before = {d.name: _json(v) for d, v in zip(cur.description or [], row, strict=True)}
        if before["version"] != body.version:
            raise ProblemError(
                409,
                "Conflict",
                "The entry was changed by someone else; reload and reapply your edit",
                type_="https://telco.local/problems/version-conflict",
                server_record=before,
            )
        await cur.execute(
            """update meta.data_dictionary set business_name = %s, description = %s, is_pii = %s,
                   is_protected_attribute = %s, allowed_values = %s, example_value = %s, updated_by = %s,
                   updated_at = now(), version = version + 1
               where column_id = %s returning *""",
            (
                body.business_name,
                body.description,
                body.is_pii,
                body.is_protected_attribute,
                body.allowed_values,
                body.example_value,
                principal.username,
                column_id,
            ),
        )
        updated = await cur.fetchone()
        after = {d.name: _json(v) for d, v in zip(cur.description or [], updated or (), strict=True)}
        await cur.execute(
            "insert into meta.dictionary_audit (column_id, actor, before_json, after_json) values (%s, %s, %s, %s)",
            (column_id, principal.username, Jsonb(before), Jsonb(after)),
        )
    return after


# ------------------------------------------------------------------ lineage
@router.get("/lineage/{model}")
async def lineage(model: str, request: Request, _: Viewer, depth: Annotated[int, Query(ge=1, le=20)] = 10) -> dict[str, Any]:
    lin: Lineage = request.app.state.lineage
    if not lin.available():
        raise ProblemError(503, "Service Unavailable", "dbt manifest not found; run dbt docs generate")
    graph = lin.graph(model, depth)
    if graph is None:
        raise ProblemError(404, "Not Found", f"No dbt model, seed, snapshot or source named {model}")
    return graph


# ------------------------------------------------------------------ data quality
@router.get("/quality/runs", response_model=Page[dict[str, Any]])
async def quality_runs(
    _: Viewer,
    pool: PoolDep,
    page: Annotated[PageParams, Depends(page_params)],
    source: Annotated[Literal["dbt", "reconciliation", "ingestion"] | None, Query()] = None,
) -> Page[dict[str, Any]]:
    where, params = ("where source = %s", [source]) if source else ("", [])
    total = (await rows(pool, f"select count(*) as n from meta.dq_runs {where}", params))[0]["n"]
    items = await rows(
        pool,
        f"select * from meta.dq_runs {where} order by started_at desc limit %s offset %s",
        [*params, page.limit, page.offset],
    )
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/quality/runs/{run_id}")
async def quality_run(run_id: str, _: Viewer, pool: PoolDep) -> dict[str, Any]:
    try:
        run = await rows(pool, "select * from meta.dq_runs where run_id = %s::uuid", [run_id])
    except Exception as exc:  # noqa: BLE001 - malformed uuid
        raise ProblemError(404, "Not Found", "Unknown run id") from exc
    if not run:
        raise ProblemError(404, "Not Found", "Unknown run id")
    results = await rows(pool, "select * from meta.dq_results where run_id = %s::uuid order by status desc, test_name", [run_id])
    return {**run[0], "results": results}


# ------------------------------------------------------------------ dimension members
@router.get("/dimensions/{dimension}/members")
async def dimension_members(dimension: str, _: Viewer, pool: PoolDep, request: Request) -> dict[str, Any]:
    if dimension not in DIMENSIONS:
        raise ProblemError(404, "Not Found", f"Unknown dimension {dimension}; available: {', '.join(DIMENSIONS)}")
    cache: dict[str, tuple[float, list[Any]]] = request.app.state.member_cache
    hit = cache.get(dimension)
    if hit and time.monotonic() - hit[0] < 300:
        members = hit[1]
    else:
        table, column = DIMENSIONS[dimension]  # both from the whitelist above
        members = [r["v"] for r in await rows(pool, f'select distinct "{column}"::text as v from {table} order by 1')]
        cache[dimension] = (time.monotonic(), members)
    return {"dimension": dimension, "members": members}


# ------------------------------------------------------------------ pipelines (Airflow)
async def _airflow_token(settings: Settings, client: httpx.AsyncClient) -> str:
    r = await client.post(
        f"{settings.airflow_api_url}/auth/token",
        json={"username": settings.airflow_username, "password": settings.airflow_password},
    )
    r.raise_for_status()
    return str(r.json()["access_token"])


@router.get("/pipelines")
async def pipelines(_: Operator, request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    if not settings.airflow_api_url:
        raise ProblemError(503, "Service Unavailable", "Airflow is not configured for this deployment")
    out = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            token = await _airflow_token(settings, client)
            headers = {"Authorization": f"Bearer {token}"}
            for dag_id in DAGS:
                d = await client.get(f"{settings.airflow_api_url}/api/v2/dags/{dag_id}", headers=headers)
                runs = await client.get(
                    f"{settings.airflow_api_url}/api/v2/dags/{dag_id}/dagRuns",
                    params={"limit": 5, "order_by": "-start_date"},
                    headers=headers,
                )
                dag = d.json() if d.status_code == 200 else {}
                out.append(
                    {
                        "dag_id": dag_id,
                        "found": d.status_code == 200,
                        "is_paused": dag.get("is_paused"),
                        "schedule": dag.get("timetable_summary") or dag.get("timetable_description"),
                        "next_run": dag.get("next_dagrun_logical_date") or dag.get("next_dagrun_run_after"),
                        "runs": [
                            {k: r.get(k) for k in ("dag_run_id", "state", "run_type", "start_date", "end_date")}
                            for r in (runs.json().get("dag_runs", []) if runs.status_code == 200 else [])
                        ],
                    }
                )
    except httpx.HTTPError as exc:
        log.warning("airflow unreachable: %s", exc)
        raise ProblemError(502, "Bad Gateway", "Airflow API is unreachable") from exc
    return {"pipelines": out}
