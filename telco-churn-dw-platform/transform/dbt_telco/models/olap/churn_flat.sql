-- Denormalised current fact: one row per customer with every dimension
-- attribute. The analytics API runs its GROUPING SETS queries against this.
-- A plain table (atomic swap on rebuild, no dependency on the fact table), so a
-- failed run never removes the OLAP layer; the aggregate MVs build on top of it.
{{ config(materialized='table', indexes=[{'columns': ['customer_id'], 'unique': True}, {'columns': ['contract_type', 'payment_method']}]) }}
select
    c.customer_id,
    c.gender,
    c.senior_citizen,
    c.partner,
    c.dependents,
    k.contract_type,
    k.paperless_billing,
    p.payment_method,
    p.is_automatic,
    s.phone_service,
    s.multiple_lines,
    s.internet_service,
    s.online_security,
    s.online_backup,
    s.device_protection,
    s.tech_support,
    s.streaming_tv,
    s.streaming_movies,
    tb.band_label        as tenure_band,
    tb.sort_order        as tenure_band_order,
    d.date               as snapshot_date,
    d.month              as snapshot_month,
    d.quarter            as snapshot_quarter,
    d.year               as snapshot_year,
    ch.churn_flag,
    ch.churn_label,
    f.tenure_months,
    f.monthly_charges,
    f.total_charges,
    f.churn_probability,
    f.customer_count
from {{ ref('fact_customer_churn') }} f
join {{ ref('dim_customer') }} c     on c.customer_key = f.customer_key
join {{ ref('dim_contract') }} k     on k.contract_key = f.contract_key
join {{ ref('dim_payment') }} p      on p.payment_key = f.payment_key
join {{ ref('dim_service') }} s      on s.service_key = f.service_key
join {{ ref('dim_tenure_band') }} tb on tb.tenure_band_key = f.tenure_band_key
join {{ ref('dim_churn') }} ch       on ch.churn_key = f.churn_key
join {{ ref('dim_date') }} d         on d.date_key = f.date_key
