-- Layer: fct
-- Tests: fct_player_fixture
-- Asserts: exactly one row exists per (season, fpl_id, fixture_id).
-- Origin: new in Phase 2
-- Tier: unit
{{ config(tags=['unit']) }}

-- fct_player_fixture must hold exactly one row per (season, fpl_id, fixture_id).
-- Staging carries one row per capture — 50k+ rows over ~1.2k keys — so a
-- failure here means the dedup in fct_player_fixture stopped collapsing them.

select
    season,
    fpl_id,
    fixture_id,
    count(*) as row_count
from {{ ref('fct_player_fixture') }}
group by season, fpl_id, fixture_id
having count(*) > 1
