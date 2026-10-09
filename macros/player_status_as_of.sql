{#
    The dim_player_status_history row in force at a moment, per player (#128).
    STUB: returns every request with null state, so each test fails on its own
    assertion. Replaced in the implementation commit.

    requests:  a relation with season, fpl_id and as_of_time; every column is
               passed through.
    history:   the status history relation; defaults to the model, and a
               literal-data test passes its own.
#}
{% macro player_status_as_of(requests, history=none) -%}
    select
        requests.*,
        cast(null as timestamp) as valid_from,
        cast(null as timestamp) as valid_to,
        cast(null as varchar)   as status,
        cast(null as integer)   as chance_of_playing_this_round,
        cast(null as integer)   as chance_of_playing_next_round,
        cast(null as varchar)   as news,
        cast(null as boolean)   as can_select,
        cast(null as boolean)   as removed,
        cast(null as integer)   as team_fpl_id,
        cast(null as integer)   as position_id
    from {{ requests }} as requests
{%- endmacro %}
