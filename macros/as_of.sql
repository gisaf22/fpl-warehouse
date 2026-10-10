{#
    The row of a relation in force at a moment, per request (#142, M5): the
    row with the greatest time strictly before as_of_time, matched on keys.
    A request with no row before it gets nulls (no backdating).

    requests:     a relation with the keys and as_of_time; every column is
                  passed through, one output row per request.
    relation:     the relation to look up: a capture-grain table, or a
                  history table by its interval start.
    time_column:  the relation's time column.
    columns:      the relation's columns to return, in order.
    keys:         matched by equality; season is same-season equality only.

    STUB (failing-tests commit): matches nothing.
#}
{% macro as_of(requests, relation, time_column, columns, keys=['season', 'fpl_id'], max_age=none) -%}
    select
        requests.*
        {%- for column in columns %},
        matched.{{ column }}
        {%- endfor %}
    from {{ requests }} as requests
    left join {{ relation }} as matched
        on false
{%- endmacro %}
