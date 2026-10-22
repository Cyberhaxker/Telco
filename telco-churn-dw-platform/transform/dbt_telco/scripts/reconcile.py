#!/usr/bin/env python3
"""Reconcile the warehouse against baseline.json and record the result in meta.dq_runs.

Exit code is 1 on any mismatch when --strict is given (CI, first run);
otherwise mismatches are recorded as warnings, because counts legitimately
change once new customers are entered.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dwconn import connect

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=str(HERE / "baseline.json"))
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--dag-run-id", default=os.environ.get("AIRFLOW_CTX_DAG_RUN_ID"))
    args = ap.parse_args()
    baseline = json.loads(Path(args.baseline).read_text())

    results: list[tuple[str, str, bool, str]] = []
    with connect() as conn, conn.cursor() as cur:
        for table, expected in baseline["row_counts"].items():
            schema, name = table.split(".")
            cur.execute(f'select count(*) from "{schema}"."{name}"')  # identifiers come from baseline.json
            n = cur.fetchone()[0]
            results.append((f"row_count:{table}", table, n == expected, f"actual={n} expected={expected}"))

        cur.execute(
            "select ch.churn_label, count(*) from marts.fact_customer_churn f "
            "join marts.dim_churn ch using (churn_key) group by 1"
        )
        actual = dict(cur.fetchall())
        for label, expected in baseline["churn_counts"].items():
            n = actual.get(label, 0)
            results.append(
                (f"churn_count:{label}", "marts.fact_customer_churn", n == expected, f"actual={n} expected={expected}")
            )

        for check in baseline["olap"]:
            cur.execute(check["sql"])
            row = cur.fetchone()
            got = list(row) if row else None
            results.append(
                (f"olap:{check['name']}", "olap", got == check["expected"], f"actual={got} expected={check['expected']}")
            )

        failed = [r for r in results if not r[2]]
        status = "pass" if not failed else ("fail" if args.strict else "warn")
        cur.execute(
            "insert into meta.dq_runs (source, dag_run_id, status, total, passed, failed, warned, finished_at) "
            "values ('reconciliation', %s, %s, %s, %s, %s, %s, now()) returning run_id",
            (
                args.dag_run_id,
                status,
                len(results),
                len(results) - len(failed),
                len(failed) if args.strict else 0,
                0 if args.strict else len(failed),
            ),
        )
        run_id = cur.fetchone()[0]
        cur.executemany(
            "insert into meta.dq_results (run_id, test_name, model, status, failures, message) values (%s, %s, %s, %s, %s, %s)",
            [
                (run_id, name, model, "pass" if ok else ("fail" if args.strict else "warn"), 0 if ok else 1, msg)
                for name, model, ok, msg in results
            ],
        )
        conn.commit()

    for name, _, ok, msg in results:
        print(f"{'PASS' if ok else 'MISMATCH':8} {name:45} {msg}")
    print(f"reconciliation: {status} ({len(results) - len(failed)}/{len(results)} checks match baseline)")
    return 1 if failed and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
