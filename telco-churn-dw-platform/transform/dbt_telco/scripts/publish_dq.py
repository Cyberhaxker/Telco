#!/usr/bin/env python3
"""Publish dbt test results (run_results.json) to meta.dq_runs / meta.dq_results."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dwconn import connect

STATUS_MAP = {"pass": "pass", "success": "pass", "warn": "warn", "fail": "fail", "error": "error", "skipped": "warn"}


def main() -> int:
    ap = argparse.ArgumentParser()
    target = os.environ.get("DBT_TARGET_PATH", "target")
    # `dbt docs generate` overwrites run_results.json, so the build's results are saved as
    # run_results_build.json right after `dbt build` (see save_build_results.sh).
    ap.add_argument("--run-results", default=str(Path(target) / "run_results_build.json"))
    ap.add_argument("--manifest", default=str(Path(target) / "manifest.json"))
    ap.add_argument("--dag-run-id", default=os.environ.get("AIRFLOW_CTX_DAG_RUN_ID"))
    args = ap.parse_args()

    results = json.loads(Path(args.run_results).read_text())
    command = results.get("args", {}).get("which")
    if command not in ("build", "test"):
        print(f"{args.run_results} was written by `dbt {command}`, not build/test - refusing to publish", file=sys.stderr)
        return 1
    nodes = json.loads(Path(args.manifest).read_text()).get("nodes", {}) if Path(args.manifest).exists() else {}
    tests = [r for r in results["results"] if r["unique_id"].startswith("test.")]
    if not tests:
        print("no test results to publish")
        return 0

    rows = []
    for r in tests:
        node = nodes.get(r["unique_id"], {})
        model = next((d.split(".")[-1] for d in node.get("depends_on", {}).get("nodes", []) if d.startswith("model.")), None)
        rows.append(
            (
                node.get("name", r["unique_id"].split(".")[-2]),
                model,
                node.get("column_name"),
                STATUS_MAP.get(r["status"], "error"),
                r.get("failures"),
                (r.get("message") or "")[:2000],
            )
        )
    counts = {s: sum(1 for row in rows if row[3] == s) for s in ("pass", "warn", "fail", "error")}
    run_status = "error" if counts["error"] else "fail" if counts["fail"] else "warn" if counts["warn"] else "pass"

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into meta.dq_runs (source, dag_run_id, status, total, passed, failed, warned, started_at, finished_at) "
            "values ('dbt', %s, %s, %s, %s, %s, %s, %s, now()) returning run_id",
            (
                args.dag_run_id,
                run_status,
                len(rows),
                counts["pass"],
                counts["fail"] + counts["error"],
                counts["warn"],
                results["metadata"]["generated_at"],
            ),
        )
        run_id = cur.fetchone()[0]
        cur.executemany(
            "insert into meta.dq_results (run_id, test_name, model, column_name, status, failures, message) "
            "values (%s, %s, %s, %s, %s, %s, %s)",
            [(run_id, *row) for row in rows],
        )
        cur.execute(
            "update meta.datasets d set row_count = s.n_live_tup, last_refreshed_at = now(), updated_at = now() "
            "from pg_stat_user_tables s where s.schemaname = d.schema_name and s.relname = d.table_name"
        )
        conn.commit()
    print(f"published {len(rows)} dbt test results: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
