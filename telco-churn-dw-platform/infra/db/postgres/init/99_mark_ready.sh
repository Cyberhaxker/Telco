#!/usr/bin/env bash
# Marker read by the healthcheck: the entrypoint's temporary server answers
# pg_isready while init scripts are still running, so readiness needs this too.
set -euo pipefail
touch /var/lib/postgresql/.telco_init_done
echo "telco_churn_dw initialisation complete"
