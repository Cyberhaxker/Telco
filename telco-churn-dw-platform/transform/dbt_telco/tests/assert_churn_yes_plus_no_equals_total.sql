-- churn_yes + churn_no must equal the number of fact rows.
select yes_n, no_n, total
from (
    select
        count(*) filter (where ch.churn_label = 'Yes') as yes_n,
        count(*) filter (where ch.churn_label = 'No')  as no_n,
        count(*)                                        as total
    from {{ ref('fact_customer_churn') }} f
    join {{ ref('dim_churn') }} ch on ch.churn_key = f.churn_key
) t
where yes_n + no_n <> total
