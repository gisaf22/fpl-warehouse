-- Layer: fct
-- Tests: fct_player_fixture
-- Asserts: the fixture holds at least one round that is fully scored but NOT
--          yet ratified — the case where the retired inference and
--          event-status disagree.
-- Origin: new with the event-status source swap
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration']) }}

-- A precondition test, in the same spirit as
-- stg_test_player_departure_present: it asserts the *fixture* still contains
-- the scenario, so the assertion above it cannot pass vacuously.
--
-- fct_test_player_fixture_ratified_matches_event_status is only a real
-- regression test for the source swap if some round in the tree has published
-- scores while event-status still calls it provisional. That is precisely the
-- window the old `both scores non-NULL` inference got wrong, and it is the
-- only condition under which old and new logic produce different answers. If
-- every round in the fixture is either unplayed or fully settled, that test
-- passes no matter which logic is wired in.
--
-- In the checked-in tree this is round 4: the 2026-09-14 element-summary
-- capture carries a final scoreline for every round-4 row, while the
-- event-status capture from the same run reports points "p" and
-- bonus_added false. Both are real, unedited captures — see EVENT-STATUS
-- CAPTURES in tests/fixtures/build_fixtures.py.
--
-- Not pinned to round 4 by number: the assertion is that the *shape* survives,
-- so re-cutting the fixture against a later window keeps the test meaningful
-- as long as it still spans a settlement transition.
--
-- Fails with a single row when no such round exists.

with disagreeing_rounds as (

    select distinct fct.round
    from {{ ref('fct_player_fixture') }} as fct
    inner join {{ ref('int_round_ratification') }} as ratification
        on ratification.round = fct.round
    where fct.team_h_score is not null
      and fct.team_a_score is not null
      and not ratification.is_ratified

)

select 'no scored-but-unratified round in the fixture' as failure
where (select count(*) from disagreeing_rounds) = 0
