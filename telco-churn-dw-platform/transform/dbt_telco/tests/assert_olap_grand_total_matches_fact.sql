-- The cube's grand-total row must agree with the fact table.
select cube.customer_count, fact.n
from {{ ref('mv_churn_cube') }} cube
cross join (select count(*) as n from {{ ref('fact_customer_churn') }}) fact
where cube.grouping_id = 15 and cube.customer_count <> fact.n
