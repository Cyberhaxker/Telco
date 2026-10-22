"""Batch ingestion: the PWA outbox and server-side CSV chunking both land here."""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Header, Query, Request, UploadFile
from sqlalchemy import func, select
from telco_common.auth import Principal, require_roles
from telco_common.pagination import Page, PageParams, page_params
from telco_common.problems import ProblemError
from telco_common.records import IBM_COLUMN_MAP, RECORD_FIELDS, from_ibm_csv_row

from ..deps import FactoryDep, SessionDep, SettingsDep, wake_relay
from ..models import IngestionBatch
from ..schemas import BatchResult, BatchSummary, CsvUploadResult
from ..service import batch_payload_bytes, checksum, process_batch, replay_if_known

router = APIRouter(prefix="/api/v1/ingest", tags=["batches"])

Submitter = Annotated[Principal, Depends(require_roles("data_entry"))]
Reviewer = Annotated[Principal, Depends(require_roles("data_entry", "data_steward"))]

# Fixed namespace so a re-uploaded file maps to the same batch ids (idempotent uploads).
CSV_NAMESPACE = uuid.UUID("5b8f0c3e-2f43-4a77-9d1e-1f0a6c2b7e10")


@router.post(
    "/batches",
    response_model=BatchResult,
    summary="Submit a batch of up to 500 records",
    description=(
        "Headers: `Idempotency-Key` (UUID) and `X-Checksum-SHA256` (hex SHA-256 of the exact body). "
        "Re-sending a key returns the original result with `replayed: true`."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"$ref": "https://telco.local/contracts/ingest-batch.v1.schema.json"}}},
        }
    },
)
async def submit_batch(
    request: Request,
    principal: Submitter,
    factory: FactoryDep,
    settings: SettingsDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_checksum_sha256: Annotated[str, Header(alias="X-Checksum-SHA256")],
) -> BatchResult:
    length = int(request.headers.get("content-length") or 0)
    if length > settings.max_payload_bytes:
        raise ProblemError(413, "Payload Too Large", f"Batch payload exceeds {settings.max_payload_bytes} bytes")
    body = await request.body()
    from starlette.concurrency import run_in_threadpool

    outcome = await run_in_threadpool(
        process_batch,
        factory,
        body=body,
        idempotency_key=idempotency_key,
        checksum_header=x_checksum_sha256,
        actor=principal.username,
        max_records=settings.max_batch_records,
        max_bytes=settings.max_payload_bytes,
    )
    wake_relay(request)
    return BatchResult(**outcome.as_dict())


@router.get("/batches/{batch_id}", response_model=BatchResult)
def get_batch(batch_id: str, session: SessionDep, _: Reviewer) -> BatchResult:
    b = session.get(IngestionBatch, batch_id)
    if b is None:
        raise ProblemError(404, "Not Found", f"Batch {batch_id} does not exist")
    if b.result_json is None:
        return BatchResult(
            batch_id=b.batch_id,
            status=b.status,
            outcome="REJECTED",
            accepted_count=0,  # type: ignore[arg-type]
            rejected_count=0,
            errors=[],
            conflicts=[],
        )
    return BatchResult(**{**b.result_json, "status": b.status})


@router.get("/batches", response_model=Page[BatchSummary])
def list_batches(
    session: SessionDep,
    _: Reviewer,
    page: Annotated[PageParams, Depends(page_params)],
    status: Annotated[str | None, Query(pattern="^(RECEIVED|VALIDATED|PUBLISHED|FAILED)$")] = None,
    with_rejections: bool = False,
) -> Page[BatchSummary]:
    base = select(IngestionBatch)
    if status:
        base = base.where(IngestionBatch.status == status)
    if with_rejections:
        base = base.where((IngestionBatch.rejected_count > 0) | (IngestionBatch.conflict_count > 0))
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(base.order_by(IngestionBatch.received_at.desc()).limit(page.limit).offset(page.offset)).scalars()
    items = [
        BatchSummary(
            batch_id=b.batch_id,
            client_id=b.client_id,
            submitted_by=b.submitted_by,
            source=b.source,
            status=b.status,
            record_count=b.record_count,
            accepted_count=b.accepted_count,
            rejected_count=b.rejected_count,
            conflict_count=b.conflict_count,
            received_at=b.received_at.isoformat(),
            processed_at=b.processed_at.isoformat() if b.processed_at else None,
        )
        for b in rows
    ]
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    """Accept the IBM Telco layout or the snake_case record layout."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProblemError(400, "Bad Request", "CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text))
    header = set(reader.fieldnames or [])
    if set(IBM_COLUMN_MAP) <= header:
        return [from_ibm_csv_row(r) for r in reader]
    if set(RECORD_FIELDS) <= header:
        out = []
        for r in reader:
            # Same conversions as the IBM layout, keyed by record field names.
            ibm = {src: r.get(dst, "") for src, dst in IBM_COLUMN_MAP.items()}
            ibm["Churn"] = {"true": "Yes", "false": "No", "1": "Yes", "0": "No"}.get(
                str(r.get("churned", "")).strip().lower(), r.get("churned", "")
            )
            rec = from_ibm_csv_row(ibm)
            if r.get("version", "").strip().isdigit():
                rec["version"] = int(r["version"])
            out.append(rec)
        return out
    missing = sorted(set(IBM_COLUMN_MAP) - header)
    raise ProblemError(
        422,
        "Unprocessable Content",
        "CSV header not recognised",
        errors=[{"field": m, "code": "missing_column", "message": f"Missing column {m}"} for m in missing[:25]],
    )


@router.post("/upload-csv", response_model=CsvUploadResult, summary="Upload a CSV; the server splits it into batches of 500")
async def upload_csv(
    request: Request,
    principal: Submitter,
    factory: FactoryDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="IBM Telco layout or snake_case record layout")],
    client_id: Annotated[str, Query(max_length=64)] = "server-upload",
) -> CsvUploadResult:
    content = await file.read(settings.max_csv_bytes + 1)
    if len(content) > settings.max_csv_bytes:
        raise ProblemError(413, "Payload Too Large", f"CSV exceeds {settings.max_csv_bytes} bytes")
    file_sha = hashlib.sha256(content).hexdigest()
    records = parse_csv(content)
    if not records:
        raise ProblemError(422, "Unprocessable Content", "CSV contains no data rows")

    from starlette.concurrency import run_in_threadpool

    size = settings.max_batch_records
    results: list[BatchResult] = []
    for chunk_no, start in enumerate(range(0, len(records), size)):
        chunk = records[start : start + size]
        batch_id = str(uuid.uuid5(CSV_NAMESPACE, f"{file_sha}:{size}:{chunk_no}"))
        outcome = await run_in_threadpool(replay_if_known, factory, batch_id)
        if outcome is None:
            body = batch_payload_bytes(batch_id, client_id, chunk, "csv")
            outcome = await run_in_threadpool(
                process_batch,
                factory,
                body=body,
                idempotency_key=batch_id,
                checksum_header=checksum(body),
                actor=principal.username,
                max_records=size,
                max_bytes=settings.max_payload_bytes,
            )
        data = outcome.as_dict()
        # Report rows relative to the whole file.
        data["errors"] = [{**e, "row": e["row"] + start} for e in data["errors"]]
        data["conflicts"] = [{**c, "row": c.get("row", 0) + start} for c in data["conflicts"]]
        results.append(BatchResult(**data))
    wake_relay(request)
    return CsvUploadResult(
        file_sha256=file_sha,
        row_count=len(records),
        accepted_count=sum(r.accepted_count for r in results),
        rejected_count=sum(r.rejected_count for r in results),
        conflict_count=sum(len(r.conflicts) for r in results),
        batches=results,
    )
