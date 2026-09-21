-- Layer: fct
-- Tests: fct_player_gameweek, fct_player_fixture
-- Asserts: a departed player's finished rounds *after* their last capture read
--          fixture_count = 0 in fct_player_gameweek, and carry no row at all in
--          fct_player_fixture.
-- Origin: new — the other half of the departure behaviour from
--         fct_test_player_gameweek_spine_covers_departed_players, which
--         asserts only that the spine row exists, not what it contains.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration']) }}

-- Group membership is required, not cosmetic: this test ref()s stg_player and
-- stg_gameweek, both access: private to warehouse_internal. See CLAUDE.md,
-- "Served contract".

-- The union-across-captures player list keeps a departed player in the spine.
-- That is necessary but not sufficient: the row has to hold the *right*
-- values. A spine row that existed but silently picked up another player's
-- fixtures, or that reported NULL instead of 0, would satisfy
-- fct_test_player_gameweek_spine_covers_departed_players and still be wrong.
--
-- The property asserted here is the post-departure tail: once FPL stops
-- publishing a player, no element-summary is written for them, so no fixture
-- row can exist for any later round, and every later finished round must
-- aggregate to fixture_count = 0 — the same treatment a genuine blank
-- gameweek gets, and distinguishable from a dropped row only because the row
-- is there to inspect.
--
-- Stated generally rather than against a hardcoded fpl_id, for two reasons.
-- It keeps the test meaningful when the fixture's departed player changes,
-- and it makes the assertion safe against the live tree: `departed` is empty
-- on a build where nobody has left, so the test passes rather than failing on
-- correct data. As of 2026-09-14 the live tree is exactly that case — the
-- union of `elements` across all 128 captures is 658 and the latest capture
-- is also 658.
--
-- "After their last capture" is defined by deadline, not by round number: a
-- round whose deadline falls after the player's final capture is one FPL
-- could not have published data for them in. In the fixture tree the departed
-- player (4) last appears in the R2 capture of 2026-08-31, so rounds 3
-- (deadline 2026-09-04) and 4 (deadline 2026-09-12) are both in scope and
-- rounds 1-2, which they really played, are correctly not.
--
-- Two rounds rather than one is deliberate: a single zero row can be produced
-- by accident, and R4 plus SYNTHETIC_FINISHED in build_fixtures.py exist to
-- make the tail more than one row deep.

-- Every step is per season: a departure means absence from that season's own
-- latest capture, and its tail rounds come from that season's own calendar.

with latest_player_capture as (

    select season, run_id
    from (
        select
            season,
            run_id,
            row_number() over (
                partition by season
                order by extracted_at desc, run_id desc
            ) as capture_rank
        from (select distinct season, run_id, extracted_at from {{ ref('stg_player') }})
    )
    where capture_rank = 1

),

latest_calendar_capture as (

    select season, run_id
    from (
        select
            season,
            run_id,
            row_number() over (
                partition by season
                order by extracted_at desc, run_id desc
            ) as capture_rank
        from (select distinct season, run_id, extracted_at from {{ ref('stg_gameweek') }})
    )
    where capture_rank = 1

),

-- Players seen at some point in a season but absent from that season's most
-- recent capture.
departed as (

    select
        season,
        fpl_id,
        max(extracted_at) as last_seen_at
    from {{ ref('stg_player') }}
    where (season, fpl_id) not in (
        select (current_player.season, current_player.fpl_id)
        from {{ ref('stg_player') }} as current_player
        inner join latest_player_capture using (season, run_id)
    )
    group by season, fpl_id

),

-- The finished rounds whose deadline falls after the player stopped being
-- published — the rounds FPL cannot have served data for them in.
tail_rounds as (

    select
        departed.season,
        departed.fpl_id,
        gameweek.round
    from departed
    inner join (
        select distinct calendar.season, calendar.round, calendar.deadline_time
        from {{ ref('stg_gameweek') }} as calendar
        inner join latest_calendar_capture using (season, run_id)
        where calendar.finished
    ) as gameweek
        on gameweek.season = departed.season
    where gameweek.deadline_time > departed.last_seen_at

)

-- The aggregate must hold the round, and it must read zero.
select
    tail_rounds.season,
    tail_rounds.fpl_id,
    tail_rounds.round,
    coalesce(cast(agg.fixture_count as varchar), 'ROW MISSING') as fixture_count,
    'post-departure round is not fixture_count = 0'             as failure
from tail_rounds
left join {{ ref('fct_player_gameweek') }} as agg
    using (season, fpl_id, round)
where agg.fpl_id is null
   or agg.fixture_count <> 0

union all

-- ...and no fixture row may exist for it in the first place.
select
    tail_rounds.season,
    tail_rounds.fpl_id,
    tail_rounds.round,
    cast(count(*) as varchar)                        as fixture_count,
    'fixture rows exist for a post-departure round'  as failure
from tail_rounds
inner join {{ ref('fct_player_fixture') }} as fixtures
    using (season, fpl_id, round)
group by tail_rounds.season, tail_rounds.fpl_id, tail_rounds.round
