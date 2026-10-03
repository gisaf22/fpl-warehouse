-- =============================================================================
-- Layer: fct_ (served)
-- Model: fct_player_fixture
-- =============================================================================
--
-- Purpose:
--   The canonical per-fixture player fact. Deduplicates stg_player_fixture's
--   repeated captures down to one row per (fpl_id, fixture_id), choosing the
--   capture that reflects the ratified result.
--
-- Grain:
--   One row per (season, fpl_id, fixture_id). Asserted by
--   tests/fct_test_player_fixture_grain_uniqueness.sql.
--
--   `season` is in the grain from the outset so adding a second season later is
--   a data change, not a breaking rebuild of every downstream consumer. It comes
--   from staging. See CLAUDE.md, "Season is part of the grain".
--
-- Season scoping:
--   fpl_id, fixture_id and gameweek are all reassigned every season, so the
--   latest-capture lookup, the retraction check, the dedup partition and the
--   ratification join below all carry season. That keeps each piece of
--   within-season logic inside its own season; season is never used to relate
--   one season's rows to another's.
--
-- Dedup rule — provisional vs ratified:
--   A capture taken before a gameweek's scores are ratified carries NULL
--   team_h_score / team_a_score, and its influence / creativity / threat /
--   ict_index all read "0.0" while the real values are simply not published
--   yet. Staging is 1:1 with the raw source and so carries both provisional
--   and ratified captures of the same fixture — 558 keys have both.
--
--   Preference order:
--     1. scored (both scores non-NULL) over provisional;
--     2. within that, the most recent capture.
--
--   This ordering stays score-based deliberately. It ranks two *captures* of
--   the same fixture, and event-status is gameweek-level — it cannot say which
--   of them carries the better data. It is unrelated to the `is_ratified`
--   column below, which no longer derives from scores.
--
--   Picking arbitrarily here reintroduces the zeroed-stat corruption class
--   that fpl-ingest's settlement-transition fix exists to prevent. See
--   CLAUDE.md, "Capture dedup — provisional vs ratified".
--
-- Ordering field:
--   `extracted_at` is parsed in staging from the run_id prefix in the raw
--   object key — the only real capture timestamp available, as the payload
--   body carries none. `run_id` breaks ties between two runs that started
--   within the same second, so the ordering is total and the model is
--   deterministic.
--
-- Retracted rows:
--   FPL sometimes *removes* a history row it published earlier. Observed on
--   2026-09-03 for two mid-season transfers: each player briefly carried a
--   round-2 row for their other club's fixture, which later captures dropped
--   (fpl_id 28 lost fixture 20, fpl_id 166 lost fixture 16). Both ghosts had
--   0 minutes, 0 points and a zeroed ICT family.
--
--   Because staging accumulates every capture ever taken, a key FPL has
--   retracted would otherwise survive here forever and count as a fixture the
--   player never played — fixture_count 2 for a gameweek that was not a
--   double. The dedup rule above cannot catch it: fpl_id 166's ghost row is
--   itself ratified.
--
--   So a key is carried only while it is still present in that player's most
--   recent capture. Each payload holds the player's complete history array, so
--   absence from the newest one is a deletion by the source, not a partial
--   read. Staging keeps the retracted rows as the audit trail.
--
-- Columns:
--   Every stg_player_fixture column passes through unchanged — staging owns
--   the typing. Plus `is_ratified`,
--   false while the gameweek this fixture belongs to is still
--   mid-settlement. Consumers wanting settled data only should
--   filter on it rather than re-deriving it from the scores.
--
--   `team_fpl_id`, last, is the club the player played for in this fixture:
--   dim_fixture's home side when the row's was_home is true, its away side
--   otherwise. It is resolved per fixture, as of that fixture, never once per
--   player or per gameweek — a player transferred mid-season, even between the
--   two fixtures of a double gameweek, carries each fixture's own club. A
--   build-time lookup is known bug 1 in CLAUDE.md. The join is a left join so
--   a fixture missing from dim_fixture surfaces as a null team, which the
--   not_null test fails, rather than silently dropping the row. Team is not on
--   fct_player_gameweek, where a double-gameweek transfer has no single club.
--
-- is_ratified — sourced, not inferred:
--   The flag comes from int_gameweek_status, which rolls up FPL's own
--   event-status endpoint. It previously read `both scores are non-NULL`,
--   using scoreline publication as a proxy for points ratification. Those are
--   different events: scores appear at full time, bonus points are applied
--   hours later, so the proxy reported ratified during the settle window while
--   `bonus` was still 0. It also could not see the rest of the gameweek — a
--   player whose Saturday fixture finished read ratified while the gameweek's
--   Monday match was unplayed.
--
--   Note the meaning this sharpens: the flag is a property of the *gameweek*,
--   carried on each of its fixture rows. A fixture with a final score in a
--   gameweek that has not settled is now false, which is the correction.
--
--   Bounded fallback — gameweeks predating capture history:
--   event-status serves only the current gameweek's dates, and all three raw
--   endpoints' capture history begins 2026-08-29, after gameweek 1 of 2026-27
--   had already finished and settled. Gameweek 1 therefore appears in zero
--   event-status captures and its finality is unrecoverable from the source.
--   For a gameweek absent from event-status entirely whose fixtures kicked
--   off before that date, a final scoreline is accepted as proof of
--   ratification — safely, because such a gameweek settled weeks ago.
--
--   This is a dated, bounded backfill for one gameweek of one season, not a
--   revival of the general inference. A gameweek absent from event-status
--   with a kickoff on or after the cutoff reads false, never fallback. When raw
--   history for 2026-27 is superseded the clause becomes dead and should be
--   deleted rather than re-dated. See CLAUDE.md, "Gameweek ratification".
--
--   The fallback is scoped to season 2026-27 explicitly. It is a statement
--   about that season's capture history, and every closed season's fixtures
--   also kicked off before the cutoff — unscoped, it would mark them ratified
--   by accident rather than by the rule below.
--
--   Closed seasons — ratified by definition:
--   A season listed in the `closed_seasons` var is over and fully settled, and
--   its rows read is_ratified = true unconditionally. event-status cannot
--   speak for it: the endpoint serves only the current gameweek, and no
--   capture of it exists for any closed season. The override is not trusted
--   blindly — tests/fct_test_player_fixture_closed_season_settled.sql fails unless that
--   season's own latest calendar reports every gameweek finished and
--   data_checked, and fails if the live season is ever listed as closed. The
--   override reads a season's own rows only; it never consults another
--   season's data.
-- =============================================================================

with captures as (

    select * from {{ ref('stg_player_fixture') }}

),

-- The single newest capture of each player, by the same total ordering used
-- to resolve competing captures below.
latest_run_per_player as (

    select
        season,
        fpl_id,
        run_id
    from (
        select
            season,
            fpl_id,
            run_id,
            row_number() over (
                partition by season, fpl_id
                order by extracted_at desc, run_id desc
            ) as run_rank
        from (select distinct season, fpl_id, run_id, extracted_at from captures)
    )
    where run_rank = 1

),

-- Keys FPL still publishes for the player. Anything else has been retracted.
current_keys as (

    select distinct
        captures.season,
        captures.fpl_id,
        captures.fixture_id
    from captures
    inner join latest_run_per_player using (season, fpl_id, run_id)

),

ranked as (

    select
        captures.*,
        case
            -- Closed season: fully settled by definition; see header.
            when list_contains({{ closed_seasons_list() }}, captures.season)
                then true
            else coalesce(
                ratification.is_ratified,
                -- Bounded fallback for 2026-27 gameweeks predating capture
                -- history; see header.
                captures.season = '2026-27'
                    and captures.kickoff_time < timestamp '2026-08-29 00:00:00'
                    and captures.team_h_score is not null
                    and captures.team_a_score is not null
            )
        end                                                 as is_ratified,
        row_number() over (
            partition by captures.season, captures.fpl_id, captures.fixture_id
            order by
                (captures.team_h_score is not null
                    and captures.team_a_score is not null) desc,
                captures.extracted_at desc,
                captures.run_id desc
        ) as capture_rank
    from captures
    inner join current_keys using (season, fpl_id, fixture_id)
    left join {{ ref('int_gameweek_status') }} as ratification
        on ratification.season = captures.season
       and ratification.gameweek = captures.gameweek

)

select
    ranked.season,
    ranked.* exclude (season, capture_rank),
    -- The fixture's side the player was on; see header.
    case
        when ranked.was_home then fixture.team_h_fpl_id
        else fixture.team_a_fpl_id
    end                                                     as team_fpl_id
from ranked
left join {{ ref('dim_fixture') }} as fixture
    on  fixture.season = ranked.season
    and fixture.fixture_id = ranked.fixture_id
where ranked.capture_rank = 1
