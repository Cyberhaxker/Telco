-- Operational records (MySQL extract) flattened to one row per customer.
-- Customers without a complete subscription are not yet analysable and are skipped.
select
    c.customer_id,
    c.gender,
    c.senior_citizen,
    c.partner,
    c.dependents,
    s.tenure_months,
    v.phone_service,
    v.multiple_lines,
    v.internet_service,
    v.online_security,
    v.online_backup,
    v.device_protection,
    v.tech_support,
    v.streaming_tv,
    v.streaming_movies,
    s.contract_type,
    s.paperless_billing,
    s.payment_method,
    s.monthly_charges::numeric(10, 2)                       as monthly_charges,
    s.total_charges::numeric(12, 2)                         as total_charges,
    coalesce(s.churned, false)                              as churned,
    greatest(c.updated_at, s.updated_at, v.updated_at)      as updated_at,
    'ops'::text                                             as record_source
from {{ source('raw', 'ops_customers') }} c
join {{ source('raw', 'ops_subscriptions') }} s on s.customer_id = c.customer_id
join {{ source('raw', 'ops_subscription_services') }} v on v.subscription_id = s.subscription_id
