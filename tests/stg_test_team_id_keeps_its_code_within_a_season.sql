-- Layer: stg
-- Tests: stg_team
-- Asserts: within a season, each team_fpl_id maps to the same team_code in
--          every capture.
-- Origin: new in #40
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#40 AC5'}) }}

-- dim_team takes each season's latest capture. That is only sound if a team
-- id means the same club all season; a returned row is an id that named two
-- clubs within one season. Keyed by season because ids are reassigned every
-- season — the same id naming different clubs across seasons is expected.

select
    season,
    team_fpl_id,
    count(distinct team_code) as team_code_count
from {{ ref('stg_team') }}
group by season, team_fpl_id
having count(distinct team_code) > 1
