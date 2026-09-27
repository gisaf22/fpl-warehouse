-- Layer: dim
-- Tests: dim_fixture
-- Asserts: a fixture with a capture before kickoff serves that last capture's
--          difficulty and is flagged pre-kickoff.
-- Origin: new in #42
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#42 AC3'}) }}

-- Re-derived from staging against the fixture tree. Kickoff is the fixture's
-- latest capture's, because a rescheduled fixture's earlier kickoff is not
-- when it was played. The tree's difficulty never changes between captures,
-- so this cannot tell one pre-kickoff capture from another. The mocked unit
-- test fixture_difficulty_is_the_last_value_before_kickoff covers that. This
-- test covers the flag and the join on real data.
--
-- The last row fails the test if the tree has no fixture with a pre-kickoff
-- capture, so it cannot pass by checking nothing.

with latest as (

    select season, fixture_id, kickoff_time
    from {{ ref('stg_fixture') }}
    qualify row_number() over (
        partition by season, fixture_id
        order by extracted_at desc, run_id desc
    ) = 1

),

last_before_kickoff as (

    select
        stg_fixture.season,
        stg_fixture.fixture_id,
        stg_fixture.team_h_difficulty,
        stg_fixture.team_a_difficulty
    from {{ ref('stg_fixture') }} as stg_fixture
    inner join latest
        on  latest.season = stg_fixture.season
        and latest.fixture_id = stg_fixture.fixture_id
    where stg_fixture.extracted_at < latest.kickoff_time
    qualify row_number() over (
        partition by stg_fixture.season, stg_fixture.fixture_id
        order by stg_fixture.extracted_at desc, stg_fixture.run_id desc
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
    from last_before_kickoff as expected
    left join {{ ref('dim_fixture') }} as dim_fixture
        on  dim_fixture.season = expected.season
        and dim_fixture.fixture_id = expected.fixture_id
    where dim_fixture.difficulty_is_pre_kickoff is distinct from true
       or dim_fixture.team_h_difficulty is distinct from expected.team_h_difficulty
       or dim_fixture.team_a_difficulty is distinct from expected.team_a_difficulty

)

select * from mismatched

union all

select
    'no fixture with a pre-kickoff capture' as season,
    null, null, null, null, null, null
where not exists (select 1 from last_before_kickoff)
