{{ config(post_hook=["{{ add_primary_key('payment_key') }}"]) }}
select
    (row_number() over (order by payment_method))::integer  as payment_key,
    payment_method::varchar(30)                             as payment_method,
    is_automatic_payment                                    as is_automatic
from (select distinct payment_method, is_automatic_payment from {{ ref('int_customer_current') }}) d
