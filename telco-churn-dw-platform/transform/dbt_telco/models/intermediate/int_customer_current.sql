-- One current record per customer, merged from the CSV seed, the operational
-- extract and the event stream. The most recently updated version wins; on a
-- tie the source priority (ops > stream > csv) decides.
{{ config(indexes=[{'columns': ['customer_id'], 'unique': True}]) }}

with unioned as (
    select * from {{ ref('stg_csv_seed') }}
    union all
    select * from {{ ref('stg_ops_records') }}
    union all
    select * from {{ ref('stg_stream_records') }}
),
ranked as (
    select
        u.*,
        row_number() over (
            partition by customer_id
            order by updated_at desc,
                     case record_source
                         {% for src, prio in var('source_priority').items() %}when '{{ src }}' then {{ prio }} {% endfor %}
                     end desc
        ) as rn
    from unioned u
)
select
    customer_id, gender, senior_citizen, partner, dependents, tenure_months,
    phone_service, multiple_lines, internet_service, online_security, online_backup,
    device_protection, tech_support, streaming_tv, streaming_movies,
    contract_type, paperless_billing, payment_method,
    monthly_charges, total_charges, churned,
    {{ tenure_band('tenure_months') }}                  as tenure_band,
    payment_method like '%(automatic)'                  as is_automatic_payment,
    updated_at,
    record_source,
    current_date                                        as load_date
from ranked
where rn = 1
