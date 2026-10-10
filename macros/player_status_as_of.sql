{#
    The dim_player_status_history row in force at a moment, per player (#128):
    the row containing the player's last capture strictly before as_of_time.
    A player with no capture before it gets nulls (no backdating).

    requests:  a relation with season, fpl_id and as_of_time; every column is
               passed through, one output row per request.
    history:   the status history relation; defaults to the model, and a
               literal-data test passes its own.

    A thin wrapper over as_of (#142), which holds the rule: the last row whose
    valid_from is strictly before as_of_time. That is the row containing the
    last capture before it, because row boundaries are capture times and the
    history has no gaps (#126 AC5). A capture exactly at the deadline is not
    "before" it, so a row it opens never matches. Season is same-season
    equality only. No max_age: an old valid_from is a row still in force.
#}
{% macro player_status_as_of(requests, history=none) -%}
    {{ as_of(
        requests,
        history if history else ref('dim_player_status_history'),
        'valid_from',
        ['valid_from', 'valid_to', 'status', 'chance_of_playing_this_round',
         'chance_of_playing_next_round', 'news', 'can_select', 'removed',
         'team_fpl_id', 'position_id']
    ) }}
{%- endmacro %}
