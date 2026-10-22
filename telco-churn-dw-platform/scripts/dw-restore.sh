#!/usr/bin/env bash
# Restore a dump produced by dw-backup.sh into the running warehouse.
#
#   ./scripts/dw-restore.sh backups/<file>.dump
#   COMPOSE_ARGS="-p telco-dw -f docker-compose.dw.yml" ./scripts/dw-restore.sh backups/<file>.dump
#
# Runs as the superuser in a single transaction: either the whole dump is
# restored or the warehouse is left exactly as it was. Owners, grants and
# default privileges come from the dump. Other sessions are disconnected first
# because DROP would otherwise wait on their locks.
set -euo pipefail
cd "$(dirname "$0")/.."
FILE="${1:?usage: dw-restore.sh backups/<file>.dump}"
[[ -f "$FILE" ]] || { echo "no such file: $FILE" >&2; exit 1; }
if [[ -f "$FILE.sha256" ]]; then
  sha256sum -c "$FILE.sha256"
else
  echo "warning: no checksum file for $FILE" >&2
fi
set -a; source .env; set +a
read -r -a compose_args <<<"${COMPOSE_ARGS:-}"
dc() { docker compose "${compose_args[@]}" "$@"; }

echo "Disconnecting other sessions from $DW_DB"
dc exec -T dw-postgres psql -U "$DW_SUPERUSER" -d postgres -qAt -v db="$DW_DB" <<'SQL'
SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity
 WHERE datname = :'db' AND pid <> pg_backend_pid();
SQL

dc exec -T dw-postgres pg_restore -U "$DW_SUPERUSER" -d "$DW_DB" \
  --clean --if-exists --single-transaction --exit-on-error < "$FILE"
echo "Restored $FILE into $DW_DB"
