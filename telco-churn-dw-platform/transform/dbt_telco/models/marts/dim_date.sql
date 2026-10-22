{{ config(post_hook=["{{ add_primary_key('date_key') }}"], indexes=[{'columns': ['date'], 'unique': True}]) }}
select
    {{ date_key('d') }}                         as date_key,
    d::date                                     as date,
    extract(day from d)::smallint               as day,
    extract(week from d)::smallint              as week,
    extract(month from d)::smallint             as month,
    trim(to_char(d, 'Month'))::varchar(9)       as month_name,
    extract(quarter from d)::smallint           as quarter,
    extract(year from d)::smallint              as year,
    extract(isodow from d) in (6, 7)            as is_weekend
from generate_series('2010-01-01'::date, '2035-12-31'::date, interval '1 day') as g(d)
