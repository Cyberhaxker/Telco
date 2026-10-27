"""Chart datasets for the dashboard, read straight from the warehouse.

One payload feeds all five plots, so the PWA draws a consistent snapshot and the
SSE stream only has to push a single event when the warehouse changes.
"""

from __future__ import annotations

from typing import Any

from psycopg_pool import AsyncConnectionPool

from .deps import fetch, to_json_value

CHARGE_BIN = 10  # USD per histogram bin
RISK_ORDER = ("low", "medium", "high")


async def fingerprint(pool: AsyncConnectionPool) -> str:
    """Cheap change marker: moves whenever the flat table or the scores are rebuilt."""
    _, flat = await fetch(pool, "select count(*), coalesce(sum(churn_flag), 0), max(snapshot_date) from olap.churn_flat")
    _, scored = await fetch(pool, "select count(*), max(scored_at) from ml.current_predictions")
    return "|".join(str(to_json_value(v)) for v in (*flat[0], *scored[0]))


async def build_charts(pool: AsyncConnectionPool) -> dict[str, Any]:
    _, grid = await fetch(
        pool,
        """
        select contract_type, internet_service, count(*), sum(churn_flag),
               round(100.0 * sum(churn_flag) / nullif(count(*), 0), 2)
        from olap.churn_flat group by 1, 2 order by 1, 2""",
    )
    _, tenure = await fetch(
        pool,
        """
        select tenure_band, customer_count, churned_count, churn_rate_pct
        from olap.mv_churn_by_tenure_band where tenure_band <> '(All)' order by tenure_band_order""",
    )
    _, payment = await fetch(
        pool,
        """
        select payment_method, customer_count, churned_count, churn_rate_pct
        from olap.mv_churn_cube where grouping_id = 11 order by churn_rate_pct desc""",
    )
    _, charges = await fetch(
        pool,
        """
        select (floor(monthly_charges / %(w)s) * %(w)s)::int as lo,
               count(*) filter (where churn_flag = 0), count(*) filter (where churn_flag = 1)
        from olap.churn_flat group by 1 order by 1""",
        {"w": CHARGE_BIN},
    )
    _, risk = await fetch(
        pool,
        """
        select p.risk_band, count(*), round(avg(p.churn_probability), 4)
        from ml.current_predictions p join olap.churn_flat f on f.customer_id = p.customer_id and f.churn_flag = 0
        group by 1""",
    )
    contracts = sorted({r[0] for r in grid})
    services = sorted({r[1] for r in grid})
    risk_by = {r[0]: r for r in risk}
    return {
        "generated_at": (await fetch(pool, "select now()"))[1][0][0].isoformat(),
        "fingerprint": await fingerprint(pool),
        "contract_internet": {
            "rows": contracts,
            "columns": services,
            "cells": [
                {
                    "row": contracts.index(r[0]),
                    "column": services.index(r[1]),
                    "customers": r[2],
                    "churned": int(r[3]),
                    "churn_rate_pct": to_json_value(r[4]),
                }
                for r in grid
            ],
        },
        "tenure": [{"label": r[0], "customers": r[1], "churned": r[2], "churn_rate_pct": to_json_value(r[3])} for r in tenure],
        "payment": [{"label": r[0], "customers": r[1], "churned": r[2], "churn_rate_pct": to_json_value(r[3])} for r in payment],
        "charges": {
            "bin_width": CHARGE_BIN,
            "bins": [{"from": r[0], "to": r[0] + CHARGE_BIN, "retained": r[1], "churned": r[2]} for r in charges],
        },
        "risk": [
            {
                "band": b,
                "customers": risk_by[b][1] if b in risk_by else 0,
                "avg_probability": to_json_value(risk_by[b][2]) if b in risk_by else None,
            }
            for b in RISK_ORDER
        ],
    }
