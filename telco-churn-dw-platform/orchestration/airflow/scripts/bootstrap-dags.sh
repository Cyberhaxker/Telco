#!/usr/bin/env bash
# First-run bootstrap: seed MySQL from the CSV, train the first model, then run
# the warehouse refresh (which triggers scoring through its asset).
set -euo pipefail
DAGS=(seed_initial_csv ops_to_dw_daily ml_train_weekly ml_score_daily)

echo "waiting for DAGs to be parsed..."
for _ in $(seq 1 60); do
  listed=$(airflow dags list -o plain 2>/dev/null || true)
  missing=0
  for d in "${DAGS[@]}"; do grep -q "$d" <<<"$listed" || missing=1; done
  [[ $missing -eq 0 ]] && break
  sleep 5
done
for d in "${DAGS[@]}"; do airflow dags unpause "$d" >/dev/null; done

trigger() { airflow dags trigger "$1" -o plain | awk 'NR==2{print $2}'; }
state() { airflow dags list-runs "$1" -o plain 2>/dev/null | awk -v r="$2" '$2==r{print $3}'; }
wait_for() { # dag_id run_id timeout_s
  local s
  for _ in $(seq 1 $(( $3 / 10 ))); do
    s=$(state "$1" "$2")
    case "$s" in
      success) echo "$1 $2: success"; return 0 ;;
      failed) echo "$1 $2: FAILED" >&2; return 1 ;;
    esac
    sleep 10
  done
  echo "$1 $2: timed out (state=${s:-unknown})" >&2
  return 1
}

seed_run=$(trigger seed_initial_csv)
train_run=$(trigger ml_train_weekly)
echo "triggered seed_initial_csv=$seed_run ml_train_weekly=$train_run"
wait_for seed_initial_csv "$seed_run" 900
wait_for ml_train_weekly "$train_run" 1800
ops_run=$(trigger ops_to_dw_daily)
echo "triggered ops_to_dw_daily=$ops_run"
wait_for ops_to_dw_daily "$ops_run" 1800
echo "bootstrap complete; ml_score_daily runs automatically when the warehouse asset updates"
