-- Layer: fct
-- Tests: fct_player_market_snapshot
-- Asserts: every row carries its own capture's observed_at, from the capture
--          index.
-- Origin: new in #141; its total_players check left with the column in #143
--         (P3). stg_test_player_total_players_matches_capture_root holds it.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#141 AC3'}) }}

-- observed_at is checked against int_admitted_capture, the one place it is
-- defined (#104).

select
    snapshot.capture_key,
    snapshot.fpl_id,
    'observed_at differs from the capture index' as problem
from {{ ref('fct_player_market_snapshot') }} as snapshot
left join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = snapshot.capture_key
where snapshot.observed_at is distinct from admitted.observed_at
