#!/usr/bin/env bash
# dbt seed + build, keep the build's run_results for publish_dq.py, then docs
# (which overwrites run_results.json). Exit status is the build's.
set -uo pipefail
cd "$(dirname "$0")/.."
DBT="${DBT:-dbt}"
TARGET="${DBT_TARGET_PATH:-target}"
$DBT seed || exit $?
$DBT build "$@"
status=$?
cp "$TARGET/run_results.json" "$TARGET/run_results_build.json" 2>/dev/null || true
$DBT docs generate --quiet || echo "warning: dbt docs generate failed" >&2
exit $status
