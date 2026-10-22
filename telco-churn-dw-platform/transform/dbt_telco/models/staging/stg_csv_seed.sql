-- IBM CSV seed typed and renamed. TotalCharges is blank (" ") for the 11
-- customers with tenure 0; those become NULL.
select
    trim(customer_id)                                   as customer_id,
    trim(gender)                                        as gender,
    trim(senior_citizen)::smallint                      as senior_citizen,
    trim(partner)                                       as partner,
    trim(dependents)                                    as dependents,
    trim(tenure)::integer                               as tenure_months,
    trim(phone_service)                                 as phone_service,
    trim(multiple_lines)                                as multiple_lines,
    trim(internet_service)                              as internet_service,
    trim(online_security)                               as online_security,
    trim(online_backup)                                 as online_backup,
    trim(device_protection)                             as device_protection,
    trim(tech_support)                                  as tech_support,
    trim(streaming_tv)                                  as streaming_tv,
    trim(streaming_movies)                              as streaming_movies,
    trim(contract)                                      as contract_type,
    trim(paperless_billing)                             as paperless_billing,
    trim(payment_method)                                as payment_method,
    trim(monthly_charges)::numeric(10, 2)               as monthly_charges,
    nullif(trim(total_charges), '')::numeric(12, 2)     as total_charges,
    (trim(churn) = 'Yes')                               as churned,
    _loaded_at                                          as updated_at,
    'csv'::text                                         as record_source
from {{ source('raw', 'telco_csv_seed') }}
