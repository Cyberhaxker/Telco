-- Roll-up: contract_type -> contract_type + payment_method, plus the grand total.
{{ config(indexes=[{'columns': ['contract_type', 'payment_method'], 'unique': True}]) }}
select
    {{ all_label('contract_type') }},
    {{ all_label('payment_method') }},
    grouping(contract_type, payment_method)::smallint as grouping_level,
    {{ churn_measures() }}
from {{ ref('churn_flat') }} f
group by rollup (contract_type, payment_method)
