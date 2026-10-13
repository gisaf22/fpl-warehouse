-- =============================================================================
-- Layer: dim_ (dimension)
-- Model: dim_gameweek
-- =============================================================================
--
-- Purpose:
--   One deadline per gameweek, and how old the newest evidence before it was
--   (pre-deadline freshness, GLOSSARY.md), so a consumer joins deadlines from
--   one place (#169, Feature #163).
--
-- Grain:
--   (season, gameweek). Natural key, no surrogate
--   (docs/adr/0002-as-of-joins-on-natural-keys.md). Every staged capture
--   lists all 38 gameweeks; dim_test_gameweek_thirty_eight_per_admitted_season
--   holds every admitted season to 1..38.
--
-- Deadline (S2):
--   deadline_time from the season's newest staged capture by observed_at,
--   run_id breaking a repeat (#104). FPL moves deadlines; the newest value
--   wins. A passed deadline must not move (S14a), which
--   dim_test_gameweek_passed_deadline_never_changes checks on the input.
--
-- Freshness (S3, S7, S10, S12, S13):
--   Only staged captures count: an admitted capture whose payload did not
--   stage moves neither the clock nor freshness (#167 detects it).
--   capture clock          the season's newest staged capture's observed_at.
--                          Not now(): a rebuild from the same captures gives
--                          the same rows (S10).
--   last_capture_before_deadline_at
--                          the newest staged capture strictly before the
--                          deadline, through as_of (ADR 0002).
--   state_age_seconds      deadline_time minus that, in whole seconds.
--   Both are null until the deadline has passed by the capture clock, and
--   when no staged capture precedes the deadline: 2025-26's one capture
--   postdates every deadline, and 2026-27's first postdates GW1 and GW2.
-- =============================================================================

with captures as (

    select distinct season, observed_at
    from {{ ref('stg_gameweek') }}

),

capture_clock as (

    select season, max(observed_at) as capture_clock
    from captures
    group by season

),

deadlines as (

    select
        season,
        gameweek,
        deadline_time,
        deadline_time as as_of_time
    from {{ ref('stg_gameweek') }}
    qualify row_number() over (
        partition by season, gameweek
        order by observed_at desc, run_id desc
    ) = 1

),

last_capture as (

    {{ as_of('deadlines', 'captures', 'observed_at', ['observed_at'], keys=['season']) }}

)

select
    last_capture.season,
    last_capture.gameweek,
    last_capture.deadline_time,
    case
        when last_capture.deadline_time <= capture_clock.capture_clock
        then last_capture.observed_at
    end as last_capture_before_deadline_at,
    case
        when last_capture.deadline_time <= capture_clock.capture_clock
        then cast(date_diff(
            'second', last_capture.observed_at, last_capture.deadline_time
        ) as integer)
    end as state_age_seconds
from last_capture
inner join capture_clock
    on capture_clock.season = last_capture.season
