"""Connection helper shared by the dbt-side scripts (reads the same env as profiles.yml)."""

from __future__ import annotations

import os

import psycopg2


def connect():  # type: ignore[no-untyped-def]
    return psycopg2.connect(
        host=os.environ.get("DW_HOST", "dw-postgres"),
        port=int(os.environ.get("DW_PORT", "5432")),
        dbname=os.environ.get("DW_DB", "telco_churn_dw"),
        user=os.environ.get("DW_OWNER_USER", "dw_owner"),
        password=os.environ["DW_OWNER_PASSWORD"],
        application_name="dbt-scripts",
    )
