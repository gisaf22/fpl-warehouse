-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: in a season whose every staged bootstrap-static capture is at or
--          after every deadline, every row has NULL freshness.
-- Origin: new in #169 (#163 S10). Today that season is 2025-26: one capture
--         at 2026-05-26 03:46:26, last deadline 2026-05-24 13:30.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#169 AC3'}) }}

with first_capture as (

    select season, min(observed_at) as first_observed_at
    from {{ ref('stg_gameweek') }}
    group by season

),

seasons_captured_after_every_deadline as (

    select gameweeks.season
    from {{ ref('dim_gameweek') }} as gameweeks
    inner join first_capture
        on first_capture.season = gameweeks.season
    group by gameweeks.season, first_capture.first_observed_at
    having first_capture.first_observed_at >= max(gameweeks.deadline_time)

)

select gameweeks.*
from {{ ref('dim_gameweek') }} as gameweeks
inner join seasons_captured_after_every_deadline as seasons
    on seasons.season = gameweeks.season
where gameweeks.last_capture_before_deadline_at is not null
   or gameweeks.state_age_seconds is not null
