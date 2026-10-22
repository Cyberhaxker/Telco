{{ config(indexes=[{'columns': ['tenure_band'], 'unique': True}]) }}
select
    {{ all_label('tenure_band') }},
    min(tenure_band_order) as tenure_band_order,
    grouping(tenure_band)::smallint as grouping_level,
    {{ churn_measures() }}
from {{ ref('churn_flat') }} f
group by rollup (tenure_band)
