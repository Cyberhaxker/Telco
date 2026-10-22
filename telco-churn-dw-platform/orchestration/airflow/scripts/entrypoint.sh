#!/usr/bin/env bash
# Write the simple-auth-manager password file from the environment, then hand
# over to the stock Airflow entrypoint.
set -euo pipefail
if [[ -n "${AIRFLOW_ADMIN_USER:-}" && -n "${AIRFLOW_ADMIN_PASSWORD:-}" ]]; then
  file="${AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE:-/opt/airflow/simple_auth_passwords.json}"
  umask 077
  printf '{"%s": "%s"}\n' "$AIRFLOW_ADMIN_USER" "$AIRFLOW_ADMIN_PASSWORD" > "$file"
fi
exec /entrypoint "$@"
