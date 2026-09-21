-- Layer: fct
-- Tests: fct_player_fixture
-- Asserts: is_ratified equals FPL's own event-status verdict for every round
--          event-status actually covers.
-- Origin: new with the event-status source swap
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration']) }}

-- Group membership is required, not cosmetic: this test ref()s
-- int_round_ratification, which is access: private to warehouse_internal.
-- See CLAUDE.md, "Served contract".

-- is_ratified is sourced from event-status, not inferred from the scoreline.
-- This is the assertion that keeps it that way: for any round event-status
-- covers, the served value must be exactly the source's verdict.
--
-- It fails in both directions, which is the point:
--   - a row reading ratified for a round event-status calls provisional is the
--     retired inference leaking back in (scores are published at full time,
--     bonus points hours later);
--   - a row reading provisional for a ratified round is a broken join.
--
-- Rounds absent from event-status are deliberately excluded by the inner join:
-- they are the pre-history fallback's territory, covered separately. Scoping
-- this to covered rounds only is what lets the same assertion hold under the
-- fixture tier and against live S3.
--
-- Fails with one row per disagreeing key.

select
    fct.season,
    fct.fpl_id,
    fct.fixture_id,
    fct.round,
    fct.is_ratified                         as served_is_ratified,
    ratification.is_ratified                as event_status_is_ratified
from {{ ref('fct_player_fixture') }} as fct
inner join {{ ref('int_round_ratification') }} as ratification
    on ratification.season = fct.season
   and ratification.round = fct.round
where fct.is_ratified is distinct from ratification.is_ratified
