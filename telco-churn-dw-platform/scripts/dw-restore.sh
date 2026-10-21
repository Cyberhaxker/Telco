#!/usr/bin/env bash
# Restore a dump produced by dw-backup.sh into the running warehouse.
# Existing objects are dropped first (--clean). Roles must already exist,
# which is the case for any warehouse started from the telco/dw-postgres image.
set -euo pipefail
cd "$(dirname "$0")/.."
FILE="${1:?usage: dw-restore.sh backups/<file>.dump}"
[[ -f "$FILE" ]] || { echo "no such file: $FILE" >&2; exit 1; }
if [[ -f "$FILE.sha256" ]]; then sha256sum -c "$FILE.sha256"; fi
set -a; source .env; set +a
docker compose exec -T dw-postgres pg_restore -U "$DW_SUPERUSER" -d "$DW_DB" --clean --if-exists --no-owner --role=dw_owner --exit-on-error < "$FILE"
echo "Restored $FILE into $DW_DB"
