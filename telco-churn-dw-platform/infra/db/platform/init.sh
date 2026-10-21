#!/usr/bin/env bash
# Metadata databases for the platform tools (kept apart from the warehouse).
set -euo pipefail
: "${PLATFORM_DB_PASSWORD:?PLATFORM_DB_PASSWORD is required}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres -v pw="$PLATFORM_DB_PASSWORD" <<'SQL'
CREATE ROLE airflow  LOGIN PASSWORD :'pw';
CREATE ROLE keycloak LOGIN PASSWORD :'pw';
CREATE ROLE mlflow   LOGIN PASSWORD :'pw';
CREATE DATABASE airflow  OWNER airflow;
CREATE DATABASE keycloak OWNER keycloak;
CREATE DATABASE mlflow   OWNER mlflow;
REVOKE ALL ON DATABASE airflow, keycloak, mlflow FROM PUBLIC;
SQL
