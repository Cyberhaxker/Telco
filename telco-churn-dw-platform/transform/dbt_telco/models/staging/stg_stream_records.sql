-- Latest validated Kafka event per customer (payload is a full TelcoRecord).
with ranked as (
    select
        e.*,
        row_number() over (partition by e.customer_id order by e.produced_at desc, e.kafka_offset desc) as rn
    from {{ source('raw', 'ingest_events') }} e
)
select
    customer_id,
    payload ->> 'gender'                                    as gender,
    (payload ->> 'senior_citizen')::smallint                as senior_citizen,
    payload ->> 'partner'                                   as partner,
    payload ->> 'dependents'                                as dependents,
    (payload ->> 'tenure_months')::integer                  as tenure_months,
    payload ->> 'phone_service'                             as phone_service,
    payload ->> 'multiple_lines'                            as multiple_lines,
    payload ->> 'internet_service'                          as internet_service,
    payload ->> 'online_security'                           as online_security,
    payload ->> 'online_backup'                             as online_backup,
    payload ->> 'device_protection'                         as device_protection,
    payload ->> 'tech_support'                              as tech_support,
    payload ->> 'streaming_tv'                              as streaming_tv,
    payload ->> 'streaming_movies'                          as streaming_movies,
    payload ->> 'contract_type'                             as contract_type,
    payload ->> 'paperless_billing'                         as paperless_billing,
    payload ->> 'payment_method'                            as payment_method,
    (payload ->> 'monthly_charges')::numeric(10, 2)         as monthly_charges,
    (payload ->> 'total_charges')::numeric(12, 2)           as total_charges,
    (payload ->> 'churned')::boolean                        as churned,
    produced_at                                             as updated_at,
    'stream'::text                                          as record_source
from ranked
where rn = 1
