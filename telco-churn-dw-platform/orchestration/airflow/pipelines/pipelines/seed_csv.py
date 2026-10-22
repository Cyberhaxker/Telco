"""seed_initial_csv: validate the IBM CSV against the record contract and load it into MySQL telco_ops.

Idempotent: the batch id is derived from the file hash, rows are upserted and
an unchanged file is detected and skipped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from telco_common.records import from_ibm_csv_row, validate_record

from .conn import mysql_from_env

log = logging.getLogger("pipelines.seed_csv")
NAMESPACE = uuid.UUID("0c1b7a8e-4c55-4b6f-9a51-2d9b8b2f7c11")
SERVICE_FIELDS = (
    "phone_service",
    "multiple_lines",
    "internet_service",
    "online_security",
    "online_backup",
    "device_protection",
    "tech_support",
    "streaming_tv",
    "streaming_movies",
)


def months_before(d: date, months: int) -> date:
    import calendar

    y, m = divmod(d.year * 12 + (d.month - 1) - months, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def validate(path: str) -> tuple[list, list[dict], str]:
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    records, errors = [], []
    for i, row in enumerate(rows):
        rec, errs = validate_record(from_ibm_csv_row(row), i)
        if rec is None:
            errors.extend(e.as_dict() for e in errs)
        else:
            records.append(rec)
    return records, errors, digest


def load(records: list, errors: list[dict], digest: str, path: str) -> None:
    batch_id = str(uuid.uuid5(NAMESPACE, digest))
    today = datetime.now(UTC).date()
    conn = mysql_from_env("AIRFLOW_CONN_OPS_MYSQL_RW")
    try:
        with conn.cursor() as cur:
            cur.execute("select status from ingestion_batches where batch_id = %s", (batch_id,))
            existing = cur.fetchone()
            if existing and existing["status"] == "PUBLISHED":
                log.info("file %s already loaded as batch %s - nothing to do", path, batch_id)
                return
            cur.execute(
                """insert into ingestion_batches (batch_id, idempotency_key, client_id, submitted_by, source, record_count,
                       status, checksum_sha256) values (%s, %s, 'airflow', 'seed_initial_csv', 'csv', %s, 'RECEIVED', %s)
                   on duplicate key update status = 'RECEIVED'""",
                (batch_id, batch_id, len(records) + len({e["row"] for e in errors}), digest),
            )
            for chunk in range(0, len(records), 1000):
                part = records[chunk : chunk + 1000]
                cur.executemany(
                    """insert into customers (customer_id, gender, senior_citizen, partner, dependents, version)
                       values (%s, %s, %s, %s, %s, 1)
                       on duplicate key update version = if(
                           (gender, senior_citizen, partner, dependents) <=> (values(gender), values(senior_citizen), values(partner), values(dependents)),
                           version, version + 1),
                         gender = values(gender), senior_citizen = values(senior_citizen),
                         partner = values(partner), dependents = values(dependents)""",
                    [(r.customer_id, r.gender, r.senior_citizen, r.partner, r.dependents) for r in part],
                )
                cur.executemany(
                    """insert into subscriptions (customer_id, contract_type, paperless_billing, payment_method,
                           monthly_charges, total_charges, tenure_months, start_date, churned, churn_date, end_date)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       on duplicate key update contract_type = values(contract_type),
                         paperless_billing = values(paperless_billing), payment_method = values(payment_method),
                         monthly_charges = values(monthly_charges), total_charges = values(total_charges),
                         tenure_months = values(tenure_months), churned = values(churned)""",
                    [
                        (
                            r.customer_id,
                            r.contract_type,
                            r.paperless_billing,
                            r.payment_method,
                            r.monthly_charges,
                            r.total_charges,
                            r.tenure_months,
                            months_before(today, r.tenure_months),
                            r.churned,
                            today if r.churned else None,
                            today if r.churned else None,
                        )
                        for r in part
                    ],
                )
                ids = [r.customer_id for r in part]
                cur.execute(
                    f"select customer_id, subscription_id from subscriptions where customer_id in ({','.join(['%s'] * len(ids))})",
                    ids,
                )
                sub_ids = {row["customer_id"]: row["subscription_id"] for row in cur.fetchall()}
                cur.executemany(
                    f"""insert into subscription_services (subscription_id, {", ".join(SERVICE_FIELDS)})
                        values (%s, {", ".join(["%s"] * len(SERVICE_FIELDS))})
                        on duplicate key update {", ".join(f"{f} = values({f})" for f in SERVICE_FIELDS)}""",
                    [(sub_ids[r.customer_id], *(getattr(r, f) for f in SERVICE_FIELDS)) for r in part],
                )
            cur.execute("delete from ingestion_errors where batch_id = %s", (batch_id,))
            if errors:
                cur.executemany(
                    "insert into ingestion_errors (batch_id, row_number, field, error_code, message) values (%s, %s, %s, %s, %s)",
                    [(batch_id, e["row"], e["field"][:64], e["code"][:64], e["message"]) for e in errors],
                )
            result = {
                "batch_id": batch_id,
                "status": "PUBLISHED",
                "accepted_count": len(records),
                "rejected_count": len({e["row"] for e in errors}),
                "errors": errors[:500],
                "conflicts": [],
            }
            cur.execute(
                """update ingestion_batches set status = 'PUBLISHED', accepted_count = %s, rejected_count = %s,
                       processed_at = utc_timestamp(), result_json = %s where batch_id = %s""",
                (len(records), result["rejected_count"], json.dumps(result), batch_id),
            )
        conn.commit()
        log.info("seeded %d records from %s (batch %s, %d rejected rows)", len(records), path, batch_id, result["rejected_count"])
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.environ.get("SEED_CSV_PATH", "data/raw/Telco-Customer-Churn.csv"))
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--max-error-rate", type=float, default=0.01)
    args = ap.parse_args()
    records, errors, digest = validate(args.csv)
    bad_rows = len({e["row"] for e in errors})
    total = len(records) + bad_rows
    log.info("validated %s: %d rows, %d valid, %d invalid (sha256 %s)", args.csv, total, len(records), bad_rows, digest[:12])
    for e in errors[:20]:
        log.warning("row %(row)s %(field)s: %(message)s", e)
    if total == 0 or bad_rows / total > args.max_error_rate:
        log.error("error rate %.2f%% exceeds %.2f%% - not loading", 100 * bad_rows / max(total, 1), 100 * args.max_error_rate)
        return 1
    if not args.validate_only:
        load(records, errors, digest, args.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
