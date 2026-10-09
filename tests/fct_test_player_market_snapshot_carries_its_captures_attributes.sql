-- Layer: fct
-- Tests: fct_player_market_snapshot
-- Asserts: every row carries its own capture's observed_at, from the capture
--          index, and its own capture's total_players, one value per capture.
-- Origin: new in #141
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#141 AC3'}) }}

-- observed_at is checked against int_admitted_capture, the one place it is
-- defined (#104). total_players is the capture root's value (#140, checked
-- against the raw root there), so within one capture every row must agree.

with captures as (
    select
        capture_key,
        count(distinct total_players) as total_players_values
    from {{ ref('fct_player_market_snapshot') }}
    group by capture_key
)

select
    snapshot.capture_key,
    snapshot.fpl_id,
    'observed_at differs from the capture index' as problem
from {{ ref('fct_player_market_snapshot') }} as snapshot
left join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = snapshot.capture_key
where snapshot.observed_at is distinct from admitted.observed_at

union all

select capture_key, null, 'more than one total_players in the capture'
from captures
where total_players_values > 1
