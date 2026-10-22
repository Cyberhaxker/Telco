-- Fact rows whose keys do not resolve to a dimension member (expect 0).
select f.*
from {{ ref('fact_customer_churn') }} f
left join {{ ref('dim_customer') }} c     on c.customer_key = f.customer_key
left join {{ ref('dim_contract') }} k     on k.contract_key = f.contract_key
left join {{ ref('dim_service') }} s      on s.service_key = f.service_key
left join {{ ref('dim_payment') }} p      on p.payment_key = f.payment_key
left join {{ ref('dim_churn') }} ch       on ch.churn_key = f.churn_key
left join {{ ref('dim_tenure_band') }} tb on tb.tenure_band_key = f.tenure_band_key
left join {{ ref('dim_date') }} d         on d.date_key = f.date_key
where c.customer_key is null or k.contract_key is null or s.service_key is null or p.payment_key is null
   or ch.churn_key is null or tb.tenure_band_key is null or d.date_key is null
