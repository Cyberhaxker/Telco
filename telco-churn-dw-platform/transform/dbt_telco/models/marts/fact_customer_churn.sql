-- Grain: one row per current customer subscription for the load date.
{{ config(
    indexes=[
        {'columns': ['customer_key']}, {'columns': ['contract_key']}, {'columns': ['service_key']},
        {'columns': ['payment_key']}, {'columns': ['churn_key']}, {'columns': ['tenure_band_key']},
        {'columns': ['date_key'], 'type': 'brin'},
    ],
    post_hook=[
        "{{ add_primary_key('customer_key, date_key') }}",
        "{{ add_foreign_key('customer_key', ref('dim_customer')) }}",
        "{{ add_foreign_key('contract_key', ref('dim_contract')) }}",
        "{{ add_foreign_key('service_key', ref('dim_service')) }}",
        "{{ add_foreign_key('payment_key', ref('dim_payment')) }}",
        "{{ add_foreign_key('churn_key', ref('dim_churn')) }}",
        "{{ add_foreign_key('date_key', ref('dim_date')) }}",
        "{{ add_foreign_key('tenure_band_key', ref('dim_tenure_band')) }}",
    ]
) }}
select
    c.customer_key,
    k.contract_key,
    s.service_key,
    p.payment_key,
    ch.churn_key,
    {{ date_key('r.load_date') }}                    as date_key,
    tb.tenure_band_key,
    r.tenure_months,
    r.monthly_charges::numeric(10, 2)                as monthly_charges,
    r.total_charges::numeric(12, 2)                  as total_charges,
    pr.churn_probability::numeric(6, 5)              as churn_probability,
    1::integer                                       as customer_count
from {{ ref('int_customer_current') }} r
join {{ ref('dim_customer') }} c     on c.customer_id = r.customer_id and c.is_current
join {{ ref('dim_contract') }} k     on k.contract_type = r.contract_type and k.paperless_billing = r.paperless_billing
join {{ ref('dim_service') }} s      on (s.phone_service, s.multiple_lines, s.internet_service, s.online_security,
                                         s.online_backup, s.device_protection, s.tech_support, s.streaming_tv,
                                         s.streaming_movies)
                                      = (r.phone_service, r.multiple_lines, r.internet_service, r.online_security,
                                         r.online_backup, r.device_protection, r.tech_support, r.streaming_tv,
                                         r.streaming_movies)
join {{ ref('dim_payment') }} p      on p.payment_method = r.payment_method
join {{ ref('dim_churn') }} ch       on ch.churn_flag = r.churned::integer
join {{ ref('dim_tenure_band') }} tb on r.tenure_months between tb.min_months and tb.max_months
left join {{ source('ml', 'current_predictions') }} pr on pr.customer_id = r.customer_id
