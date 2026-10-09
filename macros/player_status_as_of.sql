{#
    The dim_player_status_history row in force at a moment, per player (#128):
    the row containing the player's last capture strictly before as_of_time.
    A player with no capture before it gets nulls (no backdating).

    requests:  a relation with season, fpl_id and as_of_time; every column is
               passed through, one output row per request.
    history:   the status history relation; defaults to the model, and a
               literal-data test passes its own.

    Strictly before, not the half-open [valid_from, valid_to): a capture
    exactly at the deadline is not "before" it, so a row it opens must not
    match. Row boundaries are capture times, so valid_from < as_of_time <=
    valid_to picks the row holding the last capture before it. Season is
    same-season equality only.
#}
{% macro player_status_as_of(requests, history=none) -%}
    select
        requests.*,
        history.valid_from,
        history.valid_to,
        history.status,
        history.chance_of_playing_this_round,
        history.chance_of_playing_next_round,
        history.news,
        history.can_select,
        history.removed,
        history.team_fpl_id,
        history.position_id
    from {{ requests }} as requests
    left join {{ history if history else ref('dim_player_status_history') }} as history
        on  history.season = requests.season
        and history.fpl_id = requests.fpl_id
        and history.valid_from < requests.as_of_time
        and (history.valid_to is null or history.valid_to >= requests.as_of_time)
{%- endmacro %}
