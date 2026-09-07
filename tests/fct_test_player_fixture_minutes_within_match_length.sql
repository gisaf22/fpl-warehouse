-- Layer: fct
-- Tests: fct_player_fixture
-- Asserts: minutes at fixture grain is between 0 and 90 — one match's length.
-- Origin: ported from tests/availability/sql/fct_test_minutes_range.sql
-- Tier: unit
{{ config(tags=['unit']) }}

-- The original asserted the bound on `last_gw_minutes` in a retired snapshot
-- feature table. The bound itself is a property of a single fixture, so it
-- lands on fct_player_fixture rather than on the gameweek aggregate, where a
-- double gameweek legitimately reaches 180.
--
-- Below 0 means a cast or arithmetic error; above 90 means the source row is
-- corrupt. FPL reports a full match as 90 and does not track extra time at
-- this grain, so 90 is a hard ceiling rather than a heuristic.

select
    season,
    fpl_id,
    fixture_id,
    round,
    minutes
from {{ ref('fct_player_fixture') }}
where minutes < 0
   or minutes > 90
