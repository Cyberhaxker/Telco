-- Full CUBE over the four most-used analysis dimensions (2^4 = 16 grouping sets).
{{ config(indexes=[{'columns': ['contract_type', 'payment_method', 'internet_service', 'tenure_band'], 'unique': True}]) }}
select
    {{ all_label('contract_type') }},
    {{ all_label('payment_method') }},
    {{ all_label('internet_service') }},
    {{ all_label('tenure_band') }},
    grouping(contract_type, payment_method, internet_service, tenure_band)::smallint as grouping_id,
    {{ churn_measures() }}
from {{ ref('churn_flat') }} f
group by cube (contract_type, payment_method, internet_service, tenure_band)
