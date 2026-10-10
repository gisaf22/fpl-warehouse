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
    max_age:      optional SQL interval, e.g. "interval '24 hours'". The
                  usable window is [as_of_time - max_age, as_of_time): when
                  the latest row before the moment is older than that, the
                  columns are null, never an older row's. Omitted, the lookup
                  is unbounded. Not meaningful on an interval history, whose
                  time is when a row opened (#142 P3).

    The cutoff is the caller's: as_of_time is whatever moment each request
    asks about, not wired to the gameweek deadline. Defaults for it and for
    max_age belong to the callers that need them (#142 P4, P5).

    Strictly before: a row exactly at the moment is not "before" it (#142
    P2). ASOF takes the greatest time below the moment, so it is deterministic
    only while times are unique within the keys; each relation looked up
    carries a test for that (#142 P1).
#}
{% macro as_of(requests, relation, time_column, columns, keys=['season', 'fpl_id'], max_age=none) -%}
    select
        requests.*
        {%- for column in columns %},
        {% if max_age -%}
        case
            when matched.{{ time_column }} >= requests.as_of_time - {{ max_age }}
            then matched.{{ column }}
        end as {{ column }}
        {%- else -%}
        matched.{{ column }}
        {%- endif %}
        {%- endfor %}
    from {{ requests }} as requests
    asof left join {{ relation }} as matched
        on {% for key in keys %}matched.{{ key }} = requests.{{ key }}
        and {% endfor %}requests.as_of_time > matched.{{ time_column }}
{%- endmacro %}
