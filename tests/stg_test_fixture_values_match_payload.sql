-- Layer: stg
-- Tests: stg_fixture
-- Asserts: every staged fixture's teams, gameweek, kickoff, scores, finished flag
--          and both difficulty values equal its own capture's payload.
-- Origin: new in #37
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#37 AC4'}) }}

-- Compared per capture, never against another capture of the same fixture:
-- the tree has fixtures whose kickoff moves and whose score goes from null to
-- final between captures, and each capture's row must carry that capture's
-- value. `is distinct from` treats null as a value, so a null coerced to 0 (or
-- a value nulled out) fails like any other mismatch. One row per differing
-- field, named, so a failure says what moved.
--
-- Whether a row exists at all is stg_test_fixture_one_row_per_fixture_per_capture's
-- claim; this test also fails if no staged row matches the source, so it cannot
-- pass by joining nothing.

with source_fixtures as (

    select
        admitted.season,
        admitted.run_id,
        cast(id as integer)            as fixture_id,
        team_h,
        team_a,
        event,
        kickoff_time,
        team_h_score,
        team_a_score,
        finished,
        team_h_difficulty,
        team_a_difficulty
    from (
        select {{ capture_key_from_filename() }} as capture_key, *
        from {{ source('fpl_raw', 'fixtures') }}
    ) as raw
    inner join {{ ref('int_admitted_capture') }} as admitted using (capture_key)

),

paired as (

    select
        source_fixtures.*,
        staged.team_h_fpl_id,
        staged.team_a_fpl_id,
        staged.gameweek,
        staged.kickoff_time            as staged_kickoff_time,
        staged.team_h_score            as staged_team_h_score,
        staged.team_a_score            as staged_team_a_score,
        staged.finished                as staged_finished,
        staged.team_h_difficulty       as staged_team_h_difficulty,
        staged.team_a_difficulty       as staged_team_a_difficulty
    from source_fixtures
    inner join {{ ref('stg_fixture') }} as staged
        on  staged.season     = source_fixtures.season
        and staged.run_id     = source_fixtures.run_id
        and staged.fixture_id = source_fixtures.fixture_id

),

mismatches as (

    select season, run_id, fixture_id, field
    from paired,
    lateral (
        select unnest([
            case when team_h_fpl_id            is distinct from team_h            then 'home team' end,
            case when team_a_fpl_id            is distinct from team_a            then 'away team' end,
            case when gameweek                 is distinct from event             then 'gameweek' end,
            case when staged_kickoff_time      is distinct from kickoff_time      then 'kickoff' end,
            case when staged_team_h_score      is distinct from team_h_score      then 'home score' end,
            case when staged_team_a_score      is distinct from team_a_score      then 'away score' end,
            case when staged_finished          is distinct from finished          then 'finished' end,
            case when staged_team_h_difficulty is distinct from team_h_difficulty then 'home difficulty' end,
            case when staged_team_a_difficulty is distinct from team_a_difficulty then 'away difficulty' end
        ]) as field
    )
    where field is not null

)

select season, run_id, fixture_id, field || ' differs from the payload' as failure
from mismatches

union all

select null, null, null, 'no staged fixture matches the source'
where not exists (select 1 from paired)
