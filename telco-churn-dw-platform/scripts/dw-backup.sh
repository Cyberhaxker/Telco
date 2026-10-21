#!/usr/bin/env bash
# Logical backup of the warehouse (custom format, compressed) into backups/.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
mkdir -p backups
FILE="backups/${DW_DB}-$(date +%Y%m%dT%H%M%S).dump"
docker compose exec -T dw-postgres pg_dump -U "$DW_SUPERUSER" -d "$DW_DB" -Fc -Z 6 > "$FILE"
sha256sum "$FILE" > "$FILE.sha256"
echo "Backup written to $FILE"
