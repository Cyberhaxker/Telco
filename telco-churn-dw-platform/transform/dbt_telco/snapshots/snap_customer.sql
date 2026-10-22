{% snapshot snap_customer %}
{{
    config(
        unique_key='customer_id',
        strategy='check',
        check_cols=['gender', 'senior_citizen', 'partner', 'dependents'],
        invalidate_hard_deletes=True,
    )
}}
-- SCD Type 2 history of customer attributes.
select customer_id, gender, senior_citizen, partner, dependents
from {{ ref('int_customer_current') }}
{% endsnapshot %}
