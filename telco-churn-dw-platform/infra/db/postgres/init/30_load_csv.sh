#!/usr/bin/env bash
# Land the IBM Telco CSV verbatim into raw.telco_csv_seed and check its shape.
set -euo pipefail
CSV="${DW_SEED_CSV:-/seed/Telco-Customer-Churn.csv}"

if [[ ! -f "$CSV" ]]; then
  echo "seed CSV $CSV not found - skipping raw.telco_csv_seed load" >&2
  exit 0
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v csv="$CSV" <<'SQL'
COPY raw.telco_csv_seed (
    customer_id, gender, senior_citizen, partner, dependents, tenure,
    phone_service, multiple_lines, internet_service, online_security, online_backup,
    device_protection, tech_support, streaming_tv, streaming_movies, contract,
    paperless_billing, payment_method, monthly_charges, total_charges, churn)
FROM :'csv' WITH (FORMAT csv, HEADER true);

DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM raw.telco_csv_seed;
    IF n <> 7043 THEN
        RAISE WARNING 'raw.telco_csv_seed has % rows (expected 7043)', n;
    ELSE
        RAISE NOTICE 'raw.telco_csv_seed loaded with % rows', n;
    END IF;
END $$;

ANALYZE raw.telco_csv_seed;
SQL
