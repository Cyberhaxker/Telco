#!/usr/bin/env bash
# Service users for telco_ops. Tables are created by Alembic (ingestion-api).
# The root password is passed through MYSQL_PWD so it never appears in the
# process list.
set -euo pipefail
: "${OPS_APP_PASSWORD:?}"; : "${OPS_EXTRACT_PASSWORD:?}"; : "${OPS_MONITOR_PASSWORD:?}"
MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" mysql -uroot <<SQL
CREATE USER IF NOT EXISTS 'ops_app'@'%' IDENTIFIED BY '${OPS_APP_PASSWORD}';
CREATE USER IF NOT EXISTS 'ops_extract'@'%' IDENTIFIED BY '${OPS_EXTRACT_PASSWORD}';
CREATE USER IF NOT EXISTS 'ops_monitor'@'%' IDENTIFIED BY '${OPS_MONITOR_PASSWORD}' WITH MAX_USER_CONNECTIONS 3;
-- ingestion-api: DML + DDL for Alembic migrations on telco_ops only
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES ON \`${MYSQL_DATABASE}\`.* TO 'ops_app'@'%';
-- Airflow extract: read-only on the operational schema
GRANT SELECT ON \`${MYSQL_DATABASE}\`.* TO 'ops_extract'@'%';
-- mysqld-exporter: server statistics only
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'ops_monitor'@'%';
GRANT SELECT ON performance_schema.* TO 'ops_monitor'@'%';
FLUSH PRIVILEGES;
SQL
