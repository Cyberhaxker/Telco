#!/usr/bin/env bash
# Service users for telco_ops. Tables are created by Alembic (ingestion-api).
set -euo pipefail
: "${OPS_APP_PASSWORD:?}"; : "${OPS_EXTRACT_PASSWORD:?}"
mysql -uroot -p"${MYSQL_ROOT_PASSWORD}" <<SQL
CREATE USER IF NOT EXISTS 'ops_app'@'%' IDENTIFIED BY '${OPS_APP_PASSWORD}';
CREATE USER IF NOT EXISTS 'ops_extract'@'%' IDENTIFIED BY '${OPS_EXTRACT_PASSWORD}';
-- ingestion-api: DML + DDL for Alembic migrations on telco_ops only
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES ON \`${MYSQL_DATABASE}\`.* TO 'ops_app'@'%';
-- Airflow extract + mysqld-exporter: read-only
GRANT SELECT ON \`${MYSQL_DATABASE}\`.* TO 'ops_extract'@'%';
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'ops_extract'@'%';
FLUSH PRIVILEGES;
SQL
