#!/usr/bin/env bash
# Build the warehouse images and export them as one portable tarball together
# with the compose file and an env template, so the warehouse can be moved to
# any machine that has Docker (no registry needed).
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${IMAGE_TAG:-$(date +%Y.%m.%d)}"
OUT="dist/telco-churn-dw-${TAG}"
mkdir -p "$OUT"

[[ -f .env ]] || ./scripts/generate-env.sh
export IMAGE_TAG="$TAG"
docker compose -f docker-compose.dw.yml --profile tools build

docker save "telco/dw-postgres:${TAG}" "telco/dbt:${TAG}" | gzip -6 > "$OUT/images.tar.gz"
cp docker-compose.dw.yml "$OUT/docker-compose.yml"
grep -E '^(DW_|POSTGRES_PORT)' .env.example > "$OUT/.env.example"
echo "IMAGE_TAG=${TAG}" >> "$OUT/.env.example"

# The packaged compose file must not try to build from source.
sed -i '/^\s*build:/d' "$OUT/docker-compose.yml"

cat > "$OUT/README.txt" <<EOF
Telco Churn data warehouse ${TAG}

  1. docker load -i images.tar.gz
  2. cp .env.example .env   and set every *_PASSWORD
  3. docker compose up -d
  4. docker compose --profile tools run --rm dbt-bootstrap   # builds marts + OLAP, reconciles counts
  5. psql "postgresql://dw_analytics:<password>@localhost:\${POSTGRES_PORT:-5432}/telco_churn_dw"
EOF

tar -C dist -czf "dist/telco-churn-dw-${TAG}.tar.gz" "telco-churn-dw-${TAG}"
rm -rf "$OUT"
sha256sum "dist/telco-churn-dw-${TAG}.tar.gz" | tee "dist/telco-churn-dw-${TAG}.tar.gz.sha256"
echo "Packaged warehouse: dist/telco-churn-dw-${TAG}.tar.gz"
