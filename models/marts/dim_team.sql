-- =============================================================================
-- Layer: dim_ (dimension)
-- Model: dim_team
-- =============================================================================
--
-- Purpose:
--   One row per team per season, so a team id on a fact resolves to a named
--   club within its own season.
--
-- Grain:
--   (season, team_fpl_id). team_fpl_id is reassigned every season, so season
--   is part of the key; a club present in two seasons is two rows sharing
--   team_code, never merged (decision 1 on #32).
--
-- Latest capture:
--   Each season's rows come from that season's latest bootstrap-static
--   capture only — every team in it, and nothing from earlier captures.
--   Ordered by observed_at, with run_id breaking a same-second tie, as the
--   element-summary dedup does. Sound because a team id names the same club
--   all season: tests/stg_test_team_id_keeps_its_code_within_a_season.sql.
--
-- strength:
--   Staged, not carried here (decision 4 on #32).
-- =============================================================================

with latest_capture as (

    select
        season,
        run_id
    from {{ ref('stg_team') }}
    group by season, run_id, observed_at
    qualify row_number() over (
        partition by season
        order by observed_at desc, run_id desc
    ) = 1

)

select
    stg_team.season,
    stg_team.team_fpl_id,
    stg_team.team_code,
    stg_team.team_name,
    stg_team.team_short_name
from {{ ref('stg_team') }} as stg_team
inner join latest_capture
    on  latest_capture.season = stg_team.season
    and latest_capture.run_id = stg_team.run_id
