-- Customer dimension, SCD Type 2 from the snap_customer snapshot.
{{ config(
    post_hook=["{{ add_primary_key('customer_key') }}"],
    indexes=[{'columns': ['customer_id']}]
) }}
select
    (row_number() over (order by customer_id, dbt_valid_from))::bigint  as customer_key,
    customer_id::varchar(20)                                           as customer_id,
    gender::varchar(10)                                                as gender,
    senior_citizen::smallint                                           as senior_citizen,
    partner::varchar(3)                                                as partner,
    dependents::varchar(3)                                             as dependents,
    dbt_valid_from                                                     as valid_from,
    dbt_valid_to                                                       as valid_to,
    (dbt_valid_to is null)                                             as is_current
from {{ ref('snap_customer') }}
