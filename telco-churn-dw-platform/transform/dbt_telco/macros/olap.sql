{# Standard OLAP measures over a fact/flat relation aliased as f. #}
{% macro churn_measures() -%}
    count(*)::integer                                                     as customer_count,
    sum(f.churn_flag)::integer                                            as churned_count,
    round(100.0 * sum(f.churn_flag) / nullif(count(*), 0), 2)             as churn_rate_pct,
    round(avg(f.monthly_charges), 2)                                      as avg_monthly_charges,
    round(sum(f.total_charges), 2)                                        as sum_total_charges,
    round(avg(f.tenure_months), 2)                                        as avg_tenure_months,
    round(avg(f.churn_probability), 5)                                    as avg_churn_probability
{%- endmacro %}

{# Label a ROLLUP/CUBE subtotal row as '(All)' so unique indexes work and
   REFRESH MATERIALIZED VIEW CONCURRENTLY is possible. #}
{% macro all_label(col) -%}
    case when grouping({{ col }}) = 1 then '(All)' else {{ col }}::text end as {{ col }}
{%- endmacro %}
