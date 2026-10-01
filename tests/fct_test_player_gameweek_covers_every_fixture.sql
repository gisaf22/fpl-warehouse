-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: every fixture actually played is represented in the gameweek table —
--          no (season, fpl_id, gameweek) present in fct_player_fixture is missing
--          from fct_player_gameweek.
-- Origin: new — closes the direction fct_test_player_gameweek_spine_complete
--         and fct_test_player_gameweek_fixture_count_matches do not check.
-- Tier: integration
{{ config(tags=['integration']) }}

-- The existing pair of tests both iterate outward from the gameweek table:
-- spine_complete compares it to the spine, and fixture_count_matches walks
-- `from fct_player_gameweek` and LEFT JOINs the fixture aggregate. Neither
-- ever looks at a fixture key that has no gameweek row at all, so an entire
-- player's played season could vanish from the aggregate without either
-- failing.
--
-- That is not hypothetical: int_player_gameweek_spine built its player list
-- from the latest bootstrap capture only, so a player dropped from FPL's
-- `elements` mid-season took every fixture they played out of
-- fct_player_gameweek while leaving them in fct_player_fixture. The spine now
-- unions across all captures; this test is what holds that property in place.
--
-- Scope — why this is restricted to gameweeks the aggregate covers:
--   fct_player_fixture holds any fixture that has been *played*, because
--   FPL writes a history row at kickoff. The spine is gated on `finished`,
--   which flips only once the gameweek fully settles. Between those two points a
--   whole gameweek exists at fixture grain and legitimately does not exist at
--   gameweek grain — live on 2026-09-14, where gameweek 4 was played and
--   ratified while the calendar still reported gameweeks 1-3 finished, and in
--   the fixtures tree, whose element-summary captures reach gameweek 3 while
--   only gameweeks 1-2 are finished.
--
--   An unrestricted anti-join therefore fails on correct data every matchday.
--   Restricting to gameweeks present in fct_player_gameweek keeps the assertion
--   pointed at the player axis, which is where the silent loss happens: a
--   departed player's fixtures sit in gameweeks that finished long ago, so they
--   are still fully in scope here.
--
--   DO NOT remove the restriction on the grounds that the fixture tree passes
--   without it. Since R4 and SYNTHETIC_FINISHED were added to
--   build_fixtures.py the tree's finished calendar covers every gameweek its
--   element-summary captures reach (1-4), so the unrestricted form happens to
--   return zero rows there too. That is a property of the fixture set, not of
--   the invariant: against `dev` the unrestricted form still fails for the
--   whole of any gameweek that has been played and not yet settled, which on
--   2026-09-14 was gameweek 4 at roughly 650 rows. Restoring a played-but-
--   unfinished gameweek to the fixture tree needs a capture taken between a
--   gameweek's kickoff and its `finished` flag flipping.
--
-- Coverage note: the checked-in fixture tree holds identical `elements` across
-- all three of its bootstrap captures, so this test exercises the query but
-- cannot currently fail-then-pass against a real departure. Reproducing one
-- requires a fixture capture with a player removed.

with covered_gameweeks as (

    select distinct season, gameweek
    from {{ ref('fct_player_gameweek') }}

),

played as (

    select distinct
        fixtures.season,
        fixtures.fpl_id,
        fixtures.gameweek
    from {{ ref('fct_player_fixture') }} as fixtures
    inner join covered_gameweeks using (season, gameweek)

)

select
    played.season,
    played.fpl_id,
    played.gameweek,
    'played_but_missing_from_gameweek' as failure
from played
left join {{ ref('fct_player_gameweek') }} as agg
    using (season, fpl_id, gameweek)
where agg.fpl_id is null
