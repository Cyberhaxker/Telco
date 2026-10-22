{# Primary key whose constraint/index name is unique per run, so it never collides
   with the __dbt_backup copy that still exists while post-hooks run. #}
{% macro add_primary_key(columns) -%}
    alter table {{ this }} add constraint {{ this.identifier }}_pk_{{ invocation_id | replace('-', '') | truncate(8, True, '') }}
    primary key ({{ columns }})
{%- endmacro %}

{% macro add_foreign_key(column, ref_relation, ref_column=none) -%}
    alter table {{ this }} add constraint fk_{{ this.identifier }}_{{ column }}
    foreign key ({{ column }}) references {{ ref_relation }} ({{ ref_column or column }})
{%- endmacro %}

{# YYYYMMDD integer key for a date expression. #}
{% macro date_key(expr) -%}
    (to_char({{ expr }}, 'YYYYMMDD'))::integer
{%- endmacro %}

{% macro tenure_band(expr) -%}
    case
        when {{ expr }} <= 12 then '0-12'
        when {{ expr }} <= 24 then '13-24'
        when {{ expr }} <= 48 then '25-48'
        else '49-72'
    end
{%- endmacro %}
