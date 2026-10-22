#!/usr/bin/env bash
# Apply database migrations (when enabled) before starting the API.
set -euo pipefail
if [[ "${RUN_MIGRATIONS:-false}" == "true" ]]; then
  for attempt in $(seq 1 30); do
    if alembic -c /app/alembic.ini upgrade head; then
      break
    fi
    if [[ $attempt -eq 30 ]]; then
      echo "migrations failed after $attempt attempts" >&2
      exit 1
    fi
    echo "database not ready, retrying migrations in 2s ($attempt/30)" >&2
    sleep 2
  done
fi
exec "$@"
