#!/usr/bin/env bash
# Land the IBM Telco CSV verbatim into raw.telco_csv_seed and check its shape.
# Any problem aborts initialisation, so the container never reports healthy
# with a missing or partial seed.
set -euo pipefail
CSV="${DW_SEED_CSV:-/seed/Telco-Customer-Churn.csv}"
EXPECTED_ROWS="${DW_SEED_EXPECTED_ROWS:-7043}"

if [[ ! -f "$CSV" ]]; then
  echo "seed CSV $CSV not found - set DW_SEED_CSV or rebuild the image" >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v csv="$CSV" -v expected="$EXPECTED_ROWS" <<'SQL'
COPY raw.telco_csv_seed (
    customer_id, gender, senior_citizen, partner, dependents, tenure,
    phone_service, multiple_lines, internet_service, online_security, online_backup,
    device_protection, tech_support, streaming_tv, streaming_movies, contract,
    paperless_billing, payment_method, monthly_charges, total_charges, churn)
FROM :'csv' WITH (FORMAT csv, HEADER true);

SELECT set_config('telco.expected_rows', :'expected', false);

DO $$
DECLARE
    n integer;
    expected integer := current_setting('telco.expected_rows')::integer;
BEGIN
    SELECT count(*) INTO n FROM raw.telco_csv_seed;
    IF n <> expected THEN
        RAISE EXCEPTION 'raw.telco_csv_seed has % rows, expected %', n, expected;
    END IF;
    RAISE NOTICE 'raw.telco_csv_seed loaded with % rows', n;
END $$;

ANALYZE raw.telco_csv_seed;
SQL
