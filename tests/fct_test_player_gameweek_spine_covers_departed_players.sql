-- Layer: fct
-- Tests: int_player_gameweek_spine
-- Asserts: every player seen in any bootstrap-static capture is in the spine —
--          a departure removes them from the latest `elements`, never from the
--          season's history.
-- Origin: new — the positive assertion of the spine's union-across-captures
--         player list, paired with
--         fct_test_player_gameweek_covers_every_fixture.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration']) }}

-- Group membership is required, not cosmetic: this test ref()s
-- int_player_gameweek_spine and stg_player, both access: private to
-- warehouse_internal. Without it dbt refuses to parse the test. See CLAUDE.md,
-- "Served contract".

-- int_player_gameweek_spine built its player list from the latest bootstrap
-- capture only. A player dropped from FPL's `elements` mid-season therefore
-- vanished from the spine, and with them every fixture they had played this
-- season vanished from fct_player_gameweek while remaining in
-- fct_player_fixture.
--
-- fct_test_player_gameweek_covers_every_fixture catches that from the fixture
-- side, but only as an absence of failure, and only for a departed player who
-- actually played. This test states the property directly and from the source
-- side: squad membership is cumulative, so every fpl_id staging has ever seen
-- must have spine rows. A regression to `where run_id = (select run_id from
-- latest_capture)` fails here immediately and unambiguously.
--
-- Non-vacuous because the fixture tree contains a real departure — player 4 is
-- in `elements` for the first two captures and absent from the third. That
-- case is itself asserted by stg_test_player_departure_present, so this test
-- cannot quietly become an empty comparison if the fixture is ever rebuilt
-- without it.
--
-- Against the live tree this currently passes trivially: on 2026-09-14 the
-- union of `elements` across all 128 captures was 658 players and the latest
-- capture was also 658, FPL's list having only grown (622 -> 658). That is
-- the point — the assertion is a forward guard, and the fixture tree is where
-- it has teeth today.

with ever_captured as (

    select distinct fpl_id
    from {{ ref('stg_player') }}

)

select
    ever_captured.fpl_id,
    'captured in bootstrap-static but missing from the spine' as failure
from ever_captured
left join (

    select distinct fpl_id
    from {{ ref('int_player_gameweek_spine') }}

) as spine using (fpl_id)
where spine.fpl_id is null
