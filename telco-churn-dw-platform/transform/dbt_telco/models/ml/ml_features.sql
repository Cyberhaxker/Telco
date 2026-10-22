-- Model input: one row per current customer. customer_id is an identifier
-- only and is never used as a feature. gender / senior_citizen are kept for
-- fairness reporting; training excludes them from the features by default.
{{ config(indexes=[{'columns': ['customer_id'], 'unique': True}]) }}
select
    customer_id,
    gender,
    senior_citizen,
    partner,
    dependents,
    tenure_months,
    phone_service,
    multiple_lines,
    internet_service,
    online_security,
    online_backup,
    device_protection,
    tech_support,
    streaming_tv,
    streaming_movies,
    contract_type,
    paperless_billing,
    payment_method,
    monthly_charges::float8          as monthly_charges,
    total_charges::float8            as total_charges,
    churned::integer                 as churn,
    updated_at                       as source_updated_at,
    current_timestamp                as built_at
from {{ ref('int_customer_current') }}
