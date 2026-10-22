{{ config(post_hook=["{{ add_primary_key('service_key') }}"]) }}
{% set cols = ['phone_service', 'multiple_lines', 'internet_service', 'online_security', 'online_backup',
               'device_protection', 'tech_support', 'streaming_tv', 'streaming_movies'] %}
select
    (row_number() over (order by {{ cols | join(', ') }}))::integer  as service_key,
    {% for c in cols %}{{ c }}::varchar(25) as {{ c }}{{ ',' if not loop.last }}
    {% endfor %}
from (select distinct {{ cols | join(', ') }} from {{ ref('int_customer_current') }}) d
