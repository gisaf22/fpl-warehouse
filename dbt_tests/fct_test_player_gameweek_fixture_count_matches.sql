-- fixture_count must equal the real number of fct_player_fixture rows for that
-- (season, fpl_id, round) — 0 for a blank gameweek, 1 normally, 2+ for a double.
--
-- Stronger than the fixture_count >= 0 assertion this is modelled on: it
-- catches a count inflated by undeduplicated captures as well as one deflated
-- by a dropped fixture.

with actual as (

    select
        season,
        fpl_id,
        round,
        count(*) as actual_fixture_count
    from {{ ref('fct_player_fixture') }}
    group by season, fpl_id, round

)

select
    agg.season,
    agg.fpl_id,
    agg.round,
    agg.fixture_count,
    coalesce(actual.actual_fixture_count, 0) as actual_fixture_count
from {{ ref('fct_player_gameweek') }} as agg
left join actual using (season, fpl_id, round)
where agg.fixture_count <> coalesce(actual.actual_fixture_count, 0)
