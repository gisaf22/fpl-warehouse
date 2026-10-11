-- Layer: dim
-- Tests: dim_fixture_schedule_history
-- Asserts: every staged (season, fixture_id) has at least one row, and in a
--          season with a single capture (2025-26) every fixture has exactly
--          one row, opened at that capture.
-- Origin: new in #152
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#152 AC9'}) }}

-- The single-capture rule is keyed on the capture count, not on a season
-- name: 2025-26 is the one such season today (the fixture tree holds it as
-- 380 fixtures), and a closed season ported later would be held to the same
-- rule.

with seasons as (

    select
        season,
        count(distinct capture_key) as season_captures,
        min(observed_at)            as season_first_capture
    from {{ ref('stg_fixture') }}
    group by season

),

staged as (

    select distinct
        fixtures.season,
        fixtures.fixture_id,
        seasons.season_captures,
        seasons.season_first_capture
    from {{ ref('stg_fixture') }} as fixtures
    inner join seasons
        on seasons.season = fixtures.season

),

history as (

    select
        season,
        fixture_id,
        count(*)        as history_rows,
        min(valid_from) as first_valid_from
    from {{ ref('dim_fixture_schedule_history') }}
    group by season, fixture_id

)

select
    staged.season,
    staged.fixture_id,
    staged.season_captures,
    history.history_rows,
    history.first_valid_from,
    case
        when history.history_rows is null then 'staged fixture has no row'
        when history.history_rows <> 1    then 'single-capture season has more than one row'
        else                                   'row does not open at the season''s capture'
    end as failure
from staged
left join history
    on  history.season = staged.season
    and history.fixture_id = staged.fixture_id
where history.history_rows is null
   or (staged.season_captures = 1 and history.history_rows <> 1)
   or (staged.season_captures = 1 and history.first_valid_from <> staged.season_first_capture)
