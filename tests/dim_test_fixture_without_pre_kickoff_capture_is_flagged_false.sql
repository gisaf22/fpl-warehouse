-- Layer: dim
-- Tests: dim_fixture
-- Asserts: a fixture with no capture before kickoff keeps its earliest
--          capture's difficulty and is flagged not pre-kickoff.
-- Origin: new in #42
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#42 AC4'}) }}

-- Two cases in the fixture tree: every 2025-26 fixture (one end-of-season
-- snapshot), and the live fixtures that kicked off before capture history
-- began on 2026-08-29. The earliest capture is the one closest to kickoff.
-- Kickoff is the latest capture's, as in dim_fixture.
--
-- The last two rows fail the test if either case is absent from the tree, so
-- it cannot pass by checking nothing.

with latest as (

    select season, fixture_id, kickoff_time
    from {{ ref('stg_fixture') }}
    qualify row_number() over (
        partition by season, fixture_id
        order by observed_at desc, run_id desc
    ) = 1

),

no_pre_kickoff_capture as (

    select latest.season, latest.fixture_id
    from latest
    where not exists (
        select 1
        from {{ ref('stg_fixture') }} as stg_fixture
        where stg_fixture.season = latest.season
          and stg_fixture.fixture_id = latest.fixture_id
          and stg_fixture.observed_at < latest.kickoff_time
    )

),

earliest as (

    select
        stg_fixture.season,
        stg_fixture.fixture_id,
        stg_fixture.team_h_difficulty,
        stg_fixture.team_a_difficulty
    from {{ ref('stg_fixture') }} as stg_fixture
    inner join no_pre_kickoff_capture
        on  no_pre_kickoff_capture.season = stg_fixture.season
        and no_pre_kickoff_capture.fixture_id = stg_fixture.fixture_id
    qualify row_number() over (
        partition by stg_fixture.season, stg_fixture.fixture_id
        order by stg_fixture.observed_at, stg_fixture.run_id
    ) = 1

),

mismatched as (

    select
        expected.season,
        expected.fixture_id,
        expected.team_h_difficulty        as expected_team_h_difficulty,
        dim_fixture.team_h_difficulty     as actual_team_h_difficulty,
        expected.team_a_difficulty        as expected_team_a_difficulty,
        dim_fixture.team_a_difficulty     as actual_team_a_difficulty,
        dim_fixture.difficulty_is_pre_kickoff
    from earliest as expected
    left join {{ ref('dim_fixture') }} as dim_fixture
        on  dim_fixture.season = expected.season
        and dim_fixture.fixture_id = expected.fixture_id
    where dim_fixture.difficulty_is_pre_kickoff is distinct from false
       or dim_fixture.team_h_difficulty is null
       or dim_fixture.team_a_difficulty is null
       or dim_fixture.team_h_difficulty <> expected.team_h_difficulty
       or dim_fixture.team_a_difficulty <> expected.team_a_difficulty

)

select * from mismatched

union all

select
    'no closed-season fixture without a pre-kickoff capture' as season,
    null, null, null, null, null, null
where not exists (
    select 1 from no_pre_kickoff_capture
    where list_contains({{ closed_seasons_list() }}, season)
)

union all

select
    'no live fixture without a pre-kickoff capture' as season,
    null, null, null, null, null, null
where not exists (
    select 1 from no_pre_kickoff_capture
    where not list_contains({{ closed_seasons_list() }}, season)
)
