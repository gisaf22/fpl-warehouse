-- Layer: dim
-- Tests: dim_fixture_schedule_history
-- Asserts: every staged capture of every fixture falls in exactly one row,
--          valid_from <= observed_at < valid_to (or open), and that row holds
--          exactly the capture's tracked fields.
-- Origin: new in #152
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#152 AC6'}) }}

-- Checked against stg_fixture directly, not against the model's own logic:
-- the history must reproduce every capture it was built from. On the fixture
-- tree, fixtures 44, 78 and 81 are rescheduled at the 2026-09-06 capture and
-- 31 fixtures from 161 at 2026-09-14, so a kickoff change the model misses
-- leaves those captures in a row with the old kickoff.

with matched as (

    select
        captures.season,
        captures.fixture_id,
        captures.observed_at,
        captures.capture_key,
        history.valid_from,
        count(history.valid_from) over (
            partition by captures.season, captures.fixture_id, captures.capture_key
        ) as rows_in_force,
        captures.gameweek          is distinct from history.gameweek
            or captures.kickoff_time      is distinct from history.kickoff_time
            or captures.team_h_fpl_id     is distinct from history.team_h_fpl_id
            or captures.team_a_fpl_id     is distinct from history.team_a_fpl_id
            or captures.team_h_difficulty is distinct from history.team_h_difficulty
            or captures.team_a_difficulty is distinct from history.team_a_difficulty
            as differs
    from {{ ref('stg_fixture') }} as captures
    left join {{ ref('dim_fixture_schedule_history') }} as history
        on  history.season = captures.season
        and history.fixture_id = captures.fixture_id
        and history.valid_from <= captures.observed_at
        and (history.valid_to is null or captures.observed_at < history.valid_to)

)

select
    season,
    fixture_id,
    observed_at,
    capture_key,
    valid_from,
    rows_in_force,
    case
        when rows_in_force <> 1 then 'capture is in ' || rows_in_force || ' rows, not one'
        else 'row differs from the capture'
    end as failure
from matched
where rows_in_force <> 1
   or differs
