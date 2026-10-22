-- Tables that are written by services (not by dbt). Everything is owned by
-- dw_owner so default privileges from 00_roles_and_schemas.sh apply.
\set ON_ERROR_STOP on
SET ROLE dw_owner;

-- ============================================================== raw
CREATE TABLE raw.telco_csv_seed (
    customer_id        text PRIMARY KEY,
    gender             text,
    senior_citizen     text,
    partner            text,
    dependents         text,
    tenure             text,
    phone_service      text,
    multiple_lines     text,
    internet_service   text,
    online_security    text,
    online_backup      text,
    device_protection  text,
    tech_support       text,
    streaming_tv       text,
    streaming_movies   text,
    contract           text,
    paperless_billing  text,
    payment_method     text,
    monthly_charges    text,
    total_charges      text,
    churn              text,
    _loaded_at         timestamptz NOT NULL DEFAULT now(),
    _source            text NOT NULL DEFAULT 'csv:Telco-Customer-Churn.csv'
);
COMMENT ON TABLE raw.telco_csv_seed IS 'IBM Telco Customer Churn sample landed verbatim (all text) at warehouse initialisation';

-- Mirrors of MySQL telco_ops, upserted by the Airflow ops_to_dw_daily DAG.
CREATE TABLE raw.ops_customers (
    customer_id     varchar(20) PRIMARY KEY,
    gender          varchar(10),
    senior_citizen  smallint,
    partner         varchar(3),
    dependents      varchar(3),
    created_at      timestamptz,
    updated_at      timestamptz,
    version         integer,
    _loaded_at      timestamptz NOT NULL DEFAULT now(),
    _source         text NOT NULL DEFAULT 'mysql:telco_ops.customers'
);

CREATE TABLE raw.ops_subscriptions (
    subscription_id    bigint PRIMARY KEY,
    customer_id        varchar(20) NOT NULL,
    contract_type      varchar(20),
    paperless_billing  varchar(3),
    payment_method     varchar(30),
    monthly_charges    numeric(10,2),
    total_charges      numeric(12,2),
    tenure_months      integer,
    start_date         date,
    end_date           date,
    churned            boolean,
    churn_date         date,
    updated_at         timestamptz,
    _loaded_at         timestamptz NOT NULL DEFAULT now(),
    _source            text NOT NULL DEFAULT 'mysql:telco_ops.subscriptions'
);
CREATE INDEX ix_ops_subscriptions_customer ON raw.ops_subscriptions (customer_id);

CREATE TABLE raw.ops_subscription_services (
    subscription_id    bigint PRIMARY KEY,
    phone_service      varchar(3),
    multiple_lines     varchar(20),
    internet_service   varchar(20),
    online_security    varchar(25),
    online_backup      varchar(25),
    device_protection  varchar(25),
    tech_support       varchar(25),
    streaming_tv       varchar(25),
    streaming_movies   varchar(25),
    updated_at         timestamptz,
    _loaded_at         timestamptz NOT NULL DEFAULT now(),
    _source            text NOT NULL DEFAULT 'mysql:telco_ops.subscription_services'
);

-- Validated events from Kafka (stream-consumer). event_id makes the upsert idempotent.
CREATE TABLE raw.ingest_events (
    event_id        uuid PRIMARY KEY,
    event_type      text NOT NULL,
    schema_version  text NOT NULL,
    batch_id        uuid,
    customer_id     varchar(20) NOT NULL,
    produced_at     timestamptz NOT NULL,
    source          text NOT NULL,
    payload         jsonb NOT NULL,
    kafka_topic     text NOT NULL,
    kafka_partition integer NOT NULL,
    kafka_offset    bigint NOT NULL,
    _loaded_at      timestamptz NOT NULL DEFAULT now(),
    _source         text NOT NULL DEFAULT 'kafka'
);
CREATE INDEX ix_ingest_events_customer ON raw.ingest_events (customer_id, produced_at DESC);
CREATE INDEX ix_ingest_events_loaded ON raw.ingest_events (_loaded_at);

CREATE TABLE raw.ingest_dlq (
    id              bigserial PRIMARY KEY,
    event_id        uuid,
    kafka_topic     text NOT NULL,
    kafka_partition integer,
    kafka_offset    bigint,
    error_code      text NOT NULL,
    error_message   text NOT NULL,
    raw_value       text,
    reprocessed_at  timestamptz,
    _loaded_at      timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE ON raw.ingest_events TO dw_ingest;
GRANT SELECT, INSERT, UPDATE ON raw.ingest_dlq TO dw_ingest;
GRANT USAGE, SELECT ON SEQUENCE raw.ingest_dlq_id_seq TO dw_ingest;

-- ============================================================== meta
CREATE TABLE meta.datasets (
    dataset_id       text PRIMARY KEY,
    name             text NOT NULL,
    layer            text NOT NULL CHECK (layer IN ('source','raw','staging','intermediate','marts','olap','ml','legacy')),
    schema_name      text NOT NULL,
    table_name       text NOT NULL,
    description      text,
    owner            text,
    source_system    text,
    refresh_schedule text,
    row_count        bigint,
    last_refreshed_at timestamptz,
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (schema_name, table_name)
);

CREATE TABLE meta.data_dictionary (
    column_id       bigserial PRIMARY KEY,
    schema_name     text NOT NULL,
    table_name      text NOT NULL,
    column_name     text NOT NULL,
    data_type       text NOT NULL,
    business_name   text,
    description     text,
    is_pii          boolean NOT NULL DEFAULT false,
    is_protected_attribute boolean NOT NULL DEFAULT false,
    allowed_values  text[],
    example_value   text,
    updated_by      text NOT NULL DEFAULT 'system',
    updated_at      timestamptz NOT NULL DEFAULT now(),
    version         integer NOT NULL DEFAULT 1,
    UNIQUE (schema_name, table_name, column_name)
);

CREATE TABLE meta.dictionary_audit (
    id          bigserial PRIMARY KEY,
    column_id   bigint NOT NULL REFERENCES meta.data_dictionary(column_id) ON DELETE CASCADE,
    actor       text NOT NULL,
    before_json jsonb,
    after_json  jsonb,
    at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE meta.dq_runs (
    run_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source       text NOT NULL,              -- dbt | reconciliation | ingestion
    dag_run_id   text,
    status       text NOT NULL CHECK (status IN ('pass','warn','fail','error')),
    total        integer NOT NULL DEFAULT 0,
    passed       integer NOT NULL DEFAULT 0,
    failed       integer NOT NULL DEFAULT 0,
    warned       integer NOT NULL DEFAULT 0,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz
);
CREATE INDEX ix_dq_runs_started ON meta.dq_runs (started_at DESC);

CREATE TABLE meta.dq_results (
    id           bigserial PRIMARY KEY,
    run_id       uuid NOT NULL REFERENCES meta.dq_runs(run_id) ON DELETE CASCADE,
    test_name    text NOT NULL,
    model        text,
    column_name  text,
    status       text NOT NULL,
    failures     integer,
    message      text,
    executed_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_dq_results_run ON meta.dq_results (run_id);

CREATE TABLE meta.pipeline_watermarks (
    pipeline    text PRIMARY KEY,
    watermark   timestamptz NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- ============================================================== ml
CREATE TABLE ml.model_runs (
    run_id            text PRIMARY KEY,
    training_run_id   text NOT NULL,           -- groups the 4 algorithms of one training job
    model_name        text NOT NULL,
    algorithm         text NOT NULL,
    params            jsonb NOT NULL DEFAULT '{}'::jsonb,
    holdout_metrics   jsonb NOT NULL,
    cv_metrics        jsonb NOT NULL DEFAULT '{}'::jsonb,
    confusion_matrix  jsonb,
    threshold         numeric(4,3) NOT NULL DEFAULT 0.5,
    feature_importance jsonb,
    registered_version text,
    is_champion       boolean NOT NULL DEFAULT false,
    trained_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_model_runs_trained ON ml.model_runs (trained_at DESC);

CREATE TABLE ml.predictions (
    prediction_id     bigserial PRIMARY KEY,
    scoring_run_id    uuid NOT NULL,
    customer_id       varchar(20) NOT NULL,
    model_name        text NOT NULL,
    model_version     text NOT NULL,
    churn_probability numeric(6,5) NOT NULL CHECK (churn_probability BETWEEN 0 AND 1),
    predicted_label   smallint NOT NULL,
    risk_band         text NOT NULL CHECK (risk_band IN ('low','medium','high')),
    top_factors       jsonb NOT NULL DEFAULT '[]'::jsonb,
    scored_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_predictions_customer ON ml.predictions (customer_id, scored_at DESC);
CREATE INDEX ix_predictions_run ON ml.predictions (scoring_run_id);
CREATE INDEX ix_predictions_scored ON ml.predictions (scored_at);
COMMENT ON TABLE ml.predictions IS
  'Prediction history. Scoring prunes rows older than ML_PREDICTION_RETENTION_DAYS; read current values from ml.current_predictions';

-- One row per customer, upserted by every scoring run, so reads never scan history.
CREATE TABLE ml.current_predictions (
    customer_id       varchar(20) PRIMARY KEY,
    prediction_id     bigint NOT NULL,
    scoring_run_id    uuid NOT NULL,
    model_name        text NOT NULL,
    model_version     text NOT NULL,
    churn_probability numeric(6,5) NOT NULL CHECK (churn_probability BETWEEN 0 AND 1),
    predicted_label   smallint NOT NULL,
    risk_band         text NOT NULL CHECK (risk_band IN ('low','medium','high')),
    top_factors       jsonb NOT NULL DEFAULT '[]'::jsonb,
    scored_at         timestamptz NOT NULL
);
CREATE INDEX ix_current_predictions_risk ON ml.current_predictions (risk_band, churn_probability DESC);

-- Kept for compatibility with earlier queries.
CREATE VIEW ml.v_latest_predictions AS
SELECT * FROM ml.current_predictions;

CREATE TABLE ml.drift_metrics (
    id            bigserial PRIMARY KEY,
    scoring_run_id uuid NOT NULL,
    feature       text NOT NULL,
    psi           numeric(10,5) NOT NULL,
    status        text NOT NULL CHECK (status IN ('stable','moderate','significant')),
    computed_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ml.fairness_metrics (
    id            bigserial PRIMARY KEY,
    run_id        text NOT NULL,
    attribute     text NOT NULL,
    group_value   text NOT NULL,
    n             integer NOT NULL,
    positive_rate numeric(6,5),
    tpr           numeric(6,5),
    fpr           numeric(6,5),
    computed_at   timestamptz NOT NULL DEFAULT now()
);

-- Scoring writes predictions; this definer function (owned by dw_owner) is the
-- only path for dw_ml to touch the fact table.
CREATE FUNCTION ml.apply_predictions_to_fact() RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, ml, marts AS $$
DECLARE
    n integer;
BEGIN
    UPDATE marts.fact_customer_churn f
       SET churn_probability = p.churn_probability
      FROM marts.dim_customer c
      JOIN ml.current_predictions p ON p.customer_id = c.customer_id
     WHERE f.customer_key = c.customer_key
       AND f.churn_probability IS DISTINCT FROM p.churn_probability;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;
REVOKE ALL ON FUNCTION ml.apply_predictions_to_fact() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ml.apply_predictions_to_fact() TO dw_ml;

-- Tables created above existed before the default privileges applied to them
-- in some cases (views), so grant explicitly as well.
GRANT SELECT ON ALL TABLES IN SCHEMA ml TO dw_analytics;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ml TO dw_ml;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ml TO dw_ml;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA meta TO dw_meta;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA meta TO dw_meta;
GRANT SELECT ON ml.model_runs, ml.current_predictions, ml.v_latest_predictions TO dw_meta;
GRANT USAGE ON SCHEMA ml TO dw_meta;

RESET ROLE;
