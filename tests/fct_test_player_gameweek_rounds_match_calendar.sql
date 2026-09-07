-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: the rounds present in the fact are exactly the rounds the latest
--          bootstrap-static capture reports as finished — none missing, none
--          from the future.
-- Origin: ported from tests/availability/sql/int_test_gw_spine_complete.sql
--         (supersedes tests/team_performance_context/sql/int_test_event_lte_as_of.sql,
--          which asserted the no-future-rounds half against the retired as_of grain)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration']) }}

-- Group membership is required, not cosmetic: this test ref()s stg_gameweek,
-- which is access: private to warehouse_internal. Without it dbt refuses to
-- parse the test. See CLAUDE.md, "Served contract".

-- fct_test_player_gameweek_spine_complete asserts the fact matches the spine.
-- This closes the other end of the chain: that the spine's own round set still
-- matches the calendar it is built from. Between them the fact is pinned to
-- the calendar, which is what the rebuild exists to guarantee — a gameweek
-- must be present because the calendar says it happened, never because a
-- fixture for it happened to be captured.
--
-- Both directions matter and fail differently. A missing round is the original
-- silent bug: downstream rolling windows shift, and the gap is
-- indistinguishable from a gameweek that never happened. An extra round means
-- the spine's `finished` gate has slipped and the fact now carries an
-- unsettled or future round, whose fixture_count 0 rows are indistinguishable
-- from genuine blank gameweeks.

with latest_capture as (

    -- The same single capture int_player_gameweek_spine selects rounds from.
    select run_id
    from {{ ref('stg_gameweek') }}
    order by extracted_at desc, run_id desc
    limit 1

),

calendar as (

    select distinct round
    from {{ ref('stg_gameweek') }}
    where run_id = (select run_id from latest_capture)
      and finished

),

served as (

    select distinct round
    from {{ ref('fct_player_gameweek') }}

)

select
    calendar.round,
    'finished_round_missing_from_fct' as failure
from calendar
left join served using (round)
where served.round is null

union all

select
    served.round,
    'fct_round_not_finished_in_calendar' as failure
from served
left join calendar using (round)
where calendar.round is null
