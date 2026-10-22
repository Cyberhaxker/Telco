{{ config(post_hook=["{{ add_primary_key('contract_key') }}"]) }}
select
    (row_number() over (order by contract_type, paperless_billing))::integer  as contract_key,
    contract_type::varchar(20)                                               as contract_type,
    paperless_billing::varchar(3)                                            as paperless_billing
from (select distinct contract_type, paperless_billing from {{ ref('int_customer_current') }}) d
