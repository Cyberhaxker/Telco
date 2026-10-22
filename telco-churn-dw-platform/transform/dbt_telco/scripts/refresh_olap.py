#!/usr/bin/env python3
"""REFRESH MATERIALIZED VIEW CONCURRENTLY for every OLAP aggregate (readers are never blocked).

The aggregates read olap.churn_flat, which dbt rebuilds; run `dbt run --select churn_flat`
first when the fact table changed outside dbt (e.g. after scoring).
"""

from __future__ import annotations

import sys

from dwconn import connect

VIEWS = ["mv_churn_by_contract_payment", "mv_churn_by_tenure_band", "mv_churn_cube"]


def main() -> int:
    conn = connect()
    conn.autocommit = True
    with conn.cursor() as cur:
        for v in VIEWS:
            cur.execute("select 1 from pg_matviews where schemaname = 'olap' and matviewname = %s", (v,))
            if cur.fetchone() is None:
                print(f"olap.{v} does not exist yet - run dbt build first", file=sys.stderr)
                return 1
            cur.execute(f'refresh materialized view concurrently olap."{v}"')
            print(f"refreshed olap.{v}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
