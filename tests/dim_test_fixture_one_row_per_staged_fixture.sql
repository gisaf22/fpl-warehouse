-- Layer: dim
-- Tests: dim_fixture
-- Asserts: each season holds exactly as many fixtures as its captures name,
--          counted from the data rather than fixed at 380.
-- Origin: new in #42
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#42 AC1'}) }}

-- Live data has 380 fixtures a season. The fixture tree's live season has 381
-- (synthetic fixture 999, #36), so the expected count is the number of
-- distinct fixture ids in the season's staged captures. Seasons come from
-- staging, so a season missing from dim_fixture scores 0 and fails. Counting
-- over every capture rather than the latest also fails a fixture that dropped
-- out of the latest capture.

with expected as (

    select
        season,
        count(distinct fixture_id) as fixture_count
    from {{ ref('stg_fixture') }}
    group by season

),

actual as (

    select
        season,
        count(*) as fixture_count
    from {{ ref('dim_fixture') }}
    group by season

)

select
    coalesce(expected.season, actual.season) as season,
    coalesce(expected.fixture_count, 0)      as expected_count,
    coalesce(actual.fixture_count, 0)        as actual_count
from expected
full outer join actual
    on actual.season = expected.season
where coalesce(expected.fixture_count, 0) <> coalesce(actual.fixture_count, 0)
