-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: a round with fixture_count > 0 carries non-NULL kickoff times and a
--          non-NULL is_ratified, and a blank round carries none of them.
-- Origin: ported from
--         tests/availability/sql/fact_test_active_player_minutes_not_null.sql
-- Tier: unit
{{ config(tags=['unit']) }}

-- The original caught a contradiction rather than a value: a positive
-- appearance count alongside a NULL minutes window meant the LEFT JOIN had
-- produced no rows despite the count saying it had. The same contradiction is
-- available here, because first_kickoff_time, last_kickoff_time and
-- is_ratified are the aggregates that are NULL exactly when no fixture joined.
--
-- Both directions are asserted, so the test also fails if a genuinely blank
-- round somehow acquires a kickoff time — the reverse inconsistency, which the
-- original could not see.

select
    season,
    fpl_id,
    round,
    fixture_count,
    first_kickoff_time,
    last_kickoff_time,
    is_ratified
from {{ ref('fct_player_gameweek') }}
where (
        fixture_count > 0
        and (
            first_kickoff_time is null
            or last_kickoff_time is null
            or is_ratified is null
        )
      )
   or (
        fixture_count = 0
        and (
            first_kickoff_time is not null
            or last_kickoff_time is not null
            or is_ratified is not null
        )
      )
