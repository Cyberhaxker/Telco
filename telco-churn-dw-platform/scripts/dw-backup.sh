#!/usr/bin/env bash
# Logical backup of the warehouse (custom format, compressed) into backups/.
#
#   ./scripts/dw-backup.sh                         # full stack (docker-compose.yml)
#   COMPOSE_ARGS="-p telco-dw -f docker-compose.dw.yml" ./scripts/dw-backup.sh   # standalone warehouse
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
read -r -a compose_args <<<"${COMPOSE_ARGS:-}"

mkdir -p backups
FILE="backups/${DW_DB}-$(date +%Y%m%dT%H%M%S).dump"
PARTIAL="$FILE.partial"
trap 'rm -f "$PARTIAL"' EXIT

# Write to a temporary name first so a failed dump never looks like a valid backup.
docker compose "${compose_args[@]}" exec -T dw-postgres \
  pg_dump -U "$DW_SUPERUSER" -d "$DW_DB" -Fc -Z 6 > "$PARTIAL"
mv "$PARTIAL" "$FILE"
sha256sum "$FILE" > "$FILE.sha256"
echo "Backup written to $FILE"
