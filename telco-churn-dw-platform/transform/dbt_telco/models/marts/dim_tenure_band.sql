{{ config(post_hook=["{{ add_primary_key('tenure_band_key') }}"]) }}
select tenure_band_key, band_label::varchar(10) as band_label, min_months, max_months, sort_order
from {{ ref('seed_tenure_band') }}
