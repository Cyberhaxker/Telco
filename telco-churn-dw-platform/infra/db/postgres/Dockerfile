# Packaged Telco Churn data warehouse (PostgreSQL 18).
#
# On first start (empty volume) the image:
#   1. creates the warehouse schemas and least-privilege service roles
#   2. creates raw / meta / ml tables
#   3. restores the original telco_churn_dw star schema into schema "legacy"
#   4. lands the IBM Telco CSV into raw.telco_csv_seed
#   5. seeds the data dictionary and dataset registry
# The marts and OLAP layers are then built by dbt (telco/dbt image).
FROM postgres:18.6

LABEL org.opencontainers.image.title="telco-churn-dw" \
      org.opencontainers.image.description="PostgreSQL star-schema data warehouse for telecom customer-churn analytics" \
      org.opencontainers.image.licenses="PostgreSQL" \
      org.opencontainers.image.source="https://github.com/your-org/telco-churn-dw-platform"

ENV DW_SEED_CSV=/seed/Telco-Customer-Churn.csv \
    POSTGRES_INITDB_ARGS="--data-checksums --auth-host=scram-sha-256"

COPY --chown=postgres:postgres data/raw/Telco-Customer-Churn.csv /seed/Telco-Customer-Churn.csv
COPY --chown=postgres:postgres infra/db/postgres/postgresql.conf /etc/postgresql/postgresql.conf
COPY --chown=postgres:postgres infra/db/postgres/init/ /docker-entrypoint-initdb.d/
COPY --chown=postgres:postgres infra/db/postgres/seed/20_telco_churn_dw_legacy.sql.gz /docker-entrypoint-initdb.d/

HEALTHCHECK --interval=5s --timeout=5s --start-period=30s --retries=60 \
  CMD pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-telco_churn_dw}" && test -f /var/lib/postgresql/.telco_init_done

CMD ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
