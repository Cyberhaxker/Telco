-- The fact table has exactly one row per current customer.
select f.n as fact_rows, c.n as current_customers
from (select count(*) as n from {{ ref('fact_customer_churn') }}) f
cross join (select count(*) as n from {{ ref('dim_customer') }} where is_current) c
where f.n <> c.n
