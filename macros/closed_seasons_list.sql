{#
    The `closed_seasons` var as a DuckDB VARCHAR[] literal, for list_contains().
    Shared by fct_player_fixture's ratification override and the test that ties
    that override to each closed season's calendar, so the two cannot disagree
    about which seasons are closed. An empty var renders `[]::varchar[]`, which
    is valid and matches nothing.
#}
{% macro closed_seasons_list() -%}
    [{% for s in var('closed_seasons') %}'{{ s }}'{{ ', ' if not loop.last }}{% endfor %}]::varchar[]
{%- endmacro %}
