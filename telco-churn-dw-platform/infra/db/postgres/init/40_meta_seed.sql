-- Dataset registry and data dictionary for the warehouse (editable through
-- the metadata-api / PWA /metadata page afterwards).
\set ON_ERROR_STOP on
SET ROLE dw_owner;

INSERT INTO meta.datasets (dataset_id, name, layer, schema_name, table_name, description, owner, source_system, refresh_schedule) VALUES
 ('src.telco_ops',            'Operational database',          'source',  'telco_ops', '*',                   'MySQL 8.4 operational store fed by the PWA and ingestion-api', 'data_entry', 'mysql', 'continuous'),
 ('raw.telco_csv_seed',       'IBM Telco churn sample (seed)', 'raw',     'raw',       'telco_csv_seed',      'Original 7,043 x 21 CSV landed verbatim', 'data_steward', 'csv', 'once'),
 ('raw.ops_customers',        'Ops customers (extract)',       'raw',     'raw',       'ops_customers',       'Incremental extract of telco_ops.customers', 'data_steward', 'mysql', '@daily'),
 ('raw.ops_subscriptions',    'Ops subscriptions (extract)',   'raw',     'raw',       'ops_subscriptions',   'Incremental extract of telco_ops.subscriptions', 'data_steward', 'mysql', '@daily'),
 ('raw.ops_subscription_services','Ops services (extract)',    'raw',     'raw',       'ops_subscription_services','Incremental extract of telco_ops.subscription_services', 'data_steward', 'mysql', '@daily'),
 ('raw.ingest_events',        'Validated ingest events',       'raw',     'raw',       'ingest_events',       'Events consumed from Kafka ingest.*.v1 topics', 'data_steward', 'kafka', 'streaming'),
 ('marts.dim_customer',       'Customer dimension (SCD2)',     'marts',   'marts',     'dim_customer',        'One row per customer version; is_current marks the active row', 'data_steward', 'dbt', '@daily'),
 ('marts.dim_contract',       'Contract dimension',            'marts',   'marts',     'dim_contract',        'Contract type x paperless billing', 'data_steward', 'dbt', '@daily'),
 ('marts.dim_service',        'Service bundle dimension',      'marts',   'marts',     'dim_service',         'Distinct combinations of the nine service attributes', 'data_steward', 'dbt', '@daily'),
 ('marts.dim_payment',        'Payment method dimension',      'marts',   'marts',     'dim_payment',         'Payment method with automatic-payment flag', 'data_steward', 'dbt', '@daily'),
 ('marts.dim_churn',          'Churn dimension',               'marts',   'marts',     'dim_churn',           'Churn flag and label', 'data_steward', 'dbt', '@daily'),
 ('marts.dim_date',           'Date dimension',                'marts',   'marts',     'dim_date',            'Calendar 2010-2035', 'data_steward', 'dbt', '@daily'),
 ('marts.dim_tenure_band',    'Tenure band dimension',         'marts',   'marts',     'dim_tenure_band',     '0-12, 13-24, 25-48, 49-72 months', 'data_steward', 'dbt', '@daily'),
 ('marts.fact_customer_churn','Customer churn fact',           'marts',   'marts',     'fact_customer_churn', 'One row per current customer subscription snapshot', 'data_steward', 'dbt', '@daily'),
 ('olap.churn_flat','Churn flat table','olap','olap','churn_flat','Denormalised current fact, one row per customer','analyst','dbt','@daily'),
 ('olap.mv_churn_by_contract_payment','Churn by contract & payment','olap','olap',    'mv_churn_by_contract_payment', 'Materialised aggregate', 'analyst', 'dbt', '@daily'),
 ('olap.mv_churn_by_tenure_band','Churn by tenure band',       'olap',    'olap',      'mv_churn_by_tenure_band', 'Materialised aggregate', 'analyst', 'dbt', '@daily'),
 ('olap.mv_churn_cube',       'Churn cube',                    'olap',    'olap',      'mv_churn_cube',       'CUBE over contract, payment, internet service, tenure band', 'analyst', 'dbt', '@daily'),
 ('ml.predictions',           'Churn predictions',             'ml',      'ml',        'predictions',         'Batch-scored churn probability per customer', 'analyst', 'ml', '@daily'),
 ('legacy.fact_customer_churn','Legacy churn fact (pre-platform)','legacy','legacy',   'fact_customer_churn', 'Original telco_churn_dw star schema, kept read-only for comparison', 'data_steward', 'postgres', 'frozen');

INSERT INTO meta.data_dictionary (schema_name, table_name, column_name, data_type, business_name, description, is_pii, is_protected_attribute, allowed_values, example_value) VALUES
 ('marts','dim_customer','customer_key','bigint','Customer key','Surrogate key of the customer version', false, false, NULL, '1'),
 ('marts','dim_customer','customer_id','varchar(20)','Customer ID','Natural key from the operational system', true, false, NULL, '7590-VHVEG'),
 ('marts','dim_customer','gender','varchar(10)','Gender','Customer gender. Protected attribute - never used for automated decisions', true, true, ARRAY['Female','Male'], 'Female'),
 ('marts','dim_customer','senior_citizen','smallint','Senior citizen','1 if the customer is 65 or older. Protected attribute', true, true, ARRAY['0','1'], '0'),
 ('marts','dim_customer','partner','varchar(3)','Has partner','Whether the customer has a partner', false, false, ARRAY['Yes','No'], 'Yes'),
 ('marts','dim_customer','dependents','varchar(3)','Has dependents','Whether the customer has dependents', false, false, ARRAY['Yes','No'], 'No'),
 ('marts','dim_customer','valid_from','timestamptz','Valid from','SCD2 start of validity', false, false, NULL, NULL),
 ('marts','dim_customer','valid_to','timestamptz','Valid to','SCD2 end of validity (NULL for current row)', false, false, NULL, NULL),
 ('marts','dim_customer','is_current','boolean','Is current','True for the active version of the customer', false, false, NULL, 'true'),
 ('marts','dim_contract','contract_type','varchar(20)','Contract type','Contract term', false, false, ARRAY['Month-to-month','One year','Two year'], 'Month-to-month'),
 ('marts','dim_contract','paperless_billing','varchar(3)','Paperless billing','Whether the customer receives paperless bills', false, false, ARRAY['Yes','No'], 'Yes'),
 ('marts','dim_payment','payment_method','varchar(30)','Payment method','How the customer pays', false, false, ARRAY['Electronic check','Mailed check','Bank transfer (automatic)','Credit card (automatic)'], 'Electronic check'),
 ('marts','dim_payment','is_automatic','boolean','Automatic payment','True for bank transfer / credit card (automatic)', false, false, NULL, 'false'),
 ('marts','dim_service','phone_service','varchar(3)','Phone service','Has phone service', false, false, ARRAY['Yes','No'], 'No'),
 ('marts','dim_service','multiple_lines','varchar(20)','Multiple lines','Has multiple phone lines', false, false, ARRAY['Yes','No','No phone service'], 'No phone service'),
 ('marts','dim_service','internet_service','varchar(20)','Internet service','Internet service type', false, false, ARRAY['DSL','Fiber optic','No'], 'DSL'),
 ('marts','dim_service','online_security','varchar(25)','Online security','Online security add-on', false, false, ARRAY['Yes','No','No internet service'], 'No'),
 ('marts','dim_service','online_backup','varchar(25)','Online backup','Online backup add-on', false, false, ARRAY['Yes','No','No internet service'], 'Yes'),
 ('marts','dim_service','device_protection','varchar(25)','Device protection','Device protection add-on', false, false, ARRAY['Yes','No','No internet service'], 'No'),
 ('marts','dim_service','tech_support','varchar(25)','Tech support','Tech support add-on', false, false, ARRAY['Yes','No','No internet service'], 'No'),
 ('marts','dim_service','streaming_tv','varchar(25)','Streaming TV','Streaming TV add-on', false, false, ARRAY['Yes','No','No internet service'], 'No'),
 ('marts','dim_service','streaming_movies','varchar(25)','Streaming movies','Streaming movies add-on', false, false, ARRAY['Yes','No','No internet service'], 'No'),
 ('marts','dim_churn','churn_flag','smallint','Churn flag','1 = churned, 0 = retained', false, false, ARRAY['0','1'], '0'),
 ('marts','dim_churn','churn_label','varchar(3)','Churn label','Yes / No', false, false, ARRAY['Yes','No'], 'No'),
 ('marts','dim_tenure_band','band_label','varchar(10)','Tenure band','Customer tenure bucket in months', false, false, ARRAY['0-12','13-24','25-48','49-72'], '0-12'),
 ('marts','dim_date','date_key','integer','Date key','YYYYMMDD', false, false, NULL, '20261021'),
 ('marts','fact_customer_churn','tenure_months','integer','Tenure (months)','Months the customer has stayed with the company', false, false, NULL, '1'),
 ('marts','fact_customer_churn','monthly_charges','numeric(10,2)','Monthly charges','Amount charged monthly (USD)', false, false, NULL, '29.85'),
 ('marts','fact_customer_churn','total_charges','numeric(12,2)','Total charges','Total amount charged to date; NULL for brand-new customers (tenure 0)', false, false, NULL, '29.85'),
 ('marts','fact_customer_churn','churn_probability','numeric(6,5)','Churn probability','Latest champion-model probability of churn. Shows model reliance, not causation', false, false, NULL, '0.62113'),
 ('marts','fact_customer_churn','customer_count','integer','Customer count','Additive measure, always 1', false, false, NULL, '1');

RESET ROLE;

-- The original warehouse is read-only for every service role.
GRANT USAGE ON SCHEMA legacy TO dw_owner, dw_analytics, dw_meta;
GRANT SELECT ON ALL TABLES IN SCHEMA legacy TO dw_owner, dw_analytics, dw_meta;
