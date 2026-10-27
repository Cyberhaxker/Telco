#!/usr/bin/env bash
# Next.js dev server (login routes need the Next server; the app is no longer a static export).
# Users live in telco_ops.app_users: run `node apps/web/scripts/seed-users.mjs` once.
set -euo pipefail
cd "$(dirname "$0")/../../apps/web"
set -a; . ../../.env; set +a
export OPS_DB_PORT="${MYSQL_PORT_LOCAL:-3306}" NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-http://localhost:9080/api/v1}"
exec npm run dev
