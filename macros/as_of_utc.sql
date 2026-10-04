{#
    The reference "now" for age checks: the freshness_as_of var when set (unit
    tests and evidence runs pin it), else the current UTC time. Used by
    int_endpoint_freshness and the recent-unadmitted warning (#103, #104).
#}
{% macro as_of_utc() -%}
    {% if var('freshness_as_of', none) -%}
    cast('{{ var("freshness_as_of") }}' as timestamp)
    {%- else -%}
    timezone('UTC', current_timestamp)
    {%- endif %}
{%- endmacro %}
