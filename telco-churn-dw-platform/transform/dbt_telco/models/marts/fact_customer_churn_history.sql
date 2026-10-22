-- Daily snapshots (one row per customer per load date) for roll-up over
-- month -> quarter -> year. Natural values are stored instead of surrogate
-- keys because dimension keys are renumbered on every rebuild.
{{ config(
    materialized='incremental',
    unique_key=['customer_id', 'date_key'],
    incremental_strategy='delete+insert',
    indexes=[{'columns': ['date_key'], 'type': 'brin'}, {'columns': ['customer_id']}]
) }}
select
    r.customer_id,
    {{ date_key('r.load_date') }}       as date_key,
    r.contract_type,
    r.paperless_billing,
    r.payment_method,
    r.internet_service,
    r.tenure_band,
    r.tenure_months,
    r.monthly_charges,
    r.total_charges,
    r.churned::integer                  as churn_flag,
    pr.churn_probability,
    1::integer                          as customer_count
from {{ ref('int_customer_current') }} r
left join {{ source('ml', 'current_predictions') }} pr on pr.customer_id = r.customer_id
