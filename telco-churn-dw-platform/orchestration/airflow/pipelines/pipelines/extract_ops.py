"""ops_to_dw_daily step 1: incremental extract MySQL telco_ops -> PostgreSQL raw.ops_*.

Rows changed since the stored watermark (minus a safety overlap) are upserted,
so re-running the task is harmless. The watermark only advances after the
warehouse transaction commits.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta

import psycopg

from .conn import mysql_from_env, pg_dsn_from_env

log = logging.getLogger("pipelines.extract_ops")
PIPELINE = "ops_to_dw_daily"
OVERLAP = timedelta(minutes=10)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

TABLES = {
    "customers": {
        "target": "raw.ops_customers",
        "key": "customer_id",
        "columns": ["customer_id", "gender", "senior_citizen", "partner", "dependents", "created_at", "updated_at", "version"],
    },
    "subscriptions": {
        "target": "raw.ops_subscriptions",
        "key": "subscription_id",
        "columns": [
            "subscription_id",
            "customer_id",
            "contract_type",
            "paperless_billing",
            "payment_method",
            "monthly_charges",
            "total_charges",
            "tenure_months",
            "start_date",
            "end_date",
            "churned",
            "churn_date",
            "updated_at",
        ],
    },
    "subscription_services": {
        "target": "raw.ops_subscription_services",
        "key": "subscription_id",
        "columns": [
            "subscription_id",
            "phone_service",
            "multiple_lines",
            "internet_service",
            "online_security",
            "online_backup",
            "device_protection",
            "tech_support",
            "streaming_tv",
            "streaming_movies",
            "updated_at",
        ],
    },
}


# MySQL BOOLEAN is TINYINT(1) and arrives as 0/1; PostgreSQL needs real booleans.
BOOL_COLUMNS = {"churned"}


def _convert(column: str, v: object) -> object:
    if column in BOOL_COLUMNS and v is not None:
        return bool(v)
    # MySQL DATETIME columns are naive UTC (server time zone +00:00).
    return v.replace(tzinfo=UTC) if isinstance(v, datetime) and v.tzinfo is None else v


def _utc(v: object) -> object:
    return _convert("", v)


def run(full: bool = False, batch_size: int = 5000) -> dict[str, int]:
    dsn = pg_dsn_from_env("AIRFLOW_CONN_DW_POSTGRES")
    counts: dict[str, int] = {}
    with psycopg.connect(dsn, application_name="airflow-extract") as pg:
        with pg.cursor() as cur:
            cur.execute("select watermark from meta.pipeline_watermarks where pipeline = %s for update", (PIPELINE,))
            row = cur.fetchone()
            watermark = EPOCH if full or row is None else row[0]
        since = (watermark - OVERLAP) if watermark > EPOCH else EPOCH
        log.info("extracting rows updated since %s", since.isoformat())
        my = mysql_from_env("AIRFLOW_CONN_OPS_MYSQL")
        new_watermark = watermark
        try:
            for table, spec in TABLES.items():
                cols = spec["columns"]
                n = 0
                with my.cursor() as mcur:
                    mcur.execute(
                        f"select {', '.join(cols)} from {table} where updated_at > %s order by updated_at",
                        (since.replace(tzinfo=None),),
                    )
                    insert = (
                        f"insert into {spec['target']} ({', '.join(cols)}, _loaded_at) values ({', '.join(['%s'] * len(cols))}, now()) "
                        f"on conflict ({spec['key']}) do update set "
                        + ", ".join(f"{c} = excluded.{c}" for c in cols if c != spec["key"])
                        + ", _loaded_at = now()"
                    )
                    while rows := mcur.fetchmany(batch_size):
                        values = [tuple(_convert(c, r[c]) for c in cols) for r in rows]
                        with pg.cursor() as cur:
                            cur.executemany(insert, values)
                        n += len(rows)
                        latest = max(_utc(r["updated_at"]) for r in rows)
                        if latest > new_watermark:  # type: ignore[operator]
                            new_watermark = latest  # type: ignore[assignment]
                counts[table] = n
                log.info("%s -> %s: %d rows", table, spec["target"], n)
        finally:
            my.close()
        with pg.cursor() as cur:
            cur.execute(
                """insert into meta.pipeline_watermarks (pipeline, watermark, updated_at) values (%s, %s, now())
                   on conflict (pipeline) do update set watermark = excluded.watermark, updated_at = now()""",
                (PIPELINE, new_watermark),
            )
        pg.commit()
    log.info("watermark advanced to %s", new_watermark.isoformat())
    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="ignore the watermark and re-extract everything")
    args = ap.parse_args()
    run(full=args.full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
