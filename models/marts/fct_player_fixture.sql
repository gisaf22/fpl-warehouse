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
--   a data change, not a breaking rebuild of every downstream consumer. It is
--   stamped from the `season` var because fpl-ingest's raw key layout carries no
--   season segment yet — every raw object read here belongs to one season. See
--   CLAUDE.md, "Season is part of the grain".
--
-- Dedup rule — provisional vs ratified:
--   A capture taken before a round's scores are ratified carries NULL
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
--   the same fixture, and event-status is round-level — it cannot say which of
--   them carries the better data. It is unrelated to the `is_ratified` column
--   below, which no longer derives from scores.
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
--   the typing — plus `is_ratified`, false while the round this fixture belongs
--   to is still mid-settlement. Consumers wanting settled data only should
--   filter on it rather than re-deriving it from the scores.
--
-- is_ratified — sourced, not inferred:
--   The flag comes from int_round_ratification, which rolls up FPL's own
--   event-status endpoint. It previously read `both scores are non-NULL`,
--   using scoreline publication as a proxy for points ratification. Those are
--   different events: scores appear at full time, bonus points are applied
--   hours later, so the proxy reported ratified during the settle window while
--   `bonus` was still 0. It also could not see the rest of the round — a
--   player whose Saturday fixture finished read ratified while the round's
--   Monday match was unplayed.
--
--   Note the meaning this sharpens: the flag is a property of the *round*,
--   carried on each of its fixture rows. A fixture with a final score in a
--   round that has not settled is now false, which is the correction.
--
--   Bounded fallback — rounds predating capture history:
--   event-status serves only the current round's dates, and all three raw
--   endpoints' capture history begins 2026-08-29, after round 1 of 2026-27 had
--   already finished and settled. Round 1 therefore appears in zero
--   event-status captures and its finality is unrecoverable from the source.
--   For a round absent from event-status entirely whose fixtures kicked off
--   before that date, a final scoreline is accepted as proof of ratification —
--   safely, because such a round settled weeks ago.
--
--   This is a dated, bounded backfill for one round of one season, not a
--   revival of the general inference. A round absent from event-status with a
--   kickoff on or after the cutoff reads false, never fallback. When raw
--   history for 2026-27 is superseded the clause becomes dead and should be
--   deleted rather than re-dated. See CLAUDE.md, "Round ratification".
-- =============================================================================

with captures as (

    select * from {{ ref('stg_player_fixture') }}

),

-- The single newest capture of each player, by the same total ordering used
-- to resolve competing captures below.
latest_run_per_player as (

    select
        fpl_id,
        run_id
    from (
        select
            fpl_id,
            run_id,
            row_number() over (
                partition by fpl_id
                order by extracted_at desc, run_id desc
            ) as run_rank
        from (select distinct fpl_id, run_id, extracted_at from captures)
    )
    where run_rank = 1

),

-- Keys FPL still publishes for the player. Anything else has been retracted.
current_keys as (

    select distinct
        captures.fpl_id,
        captures.fixture_id
    from captures
    inner join latest_run_per_player using (fpl_id, run_id)

),

ranked as (

    select
        captures.*,
        coalesce(
            ratification.is_ratified,
            -- Bounded fallback for rounds predating capture history; see header.
            captures.kickoff_time < timestamp '2026-08-29 00:00:00'
                and captures.team_h_score is not null
                and captures.team_a_score is not null
        )                                                   as is_ratified,
        row_number() over (
            partition by captures.fpl_id, captures.fixture_id
            order by
                (captures.team_h_score is not null
                    and captures.team_a_score is not null) desc,
                captures.extracted_at desc,
                captures.run_id desc
        ) as capture_rank
    from captures
    inner join current_keys using (fpl_id, fixture_id)
    left join {{ ref('int_round_ratification') }} as ratification
        on ratification.round = captures.round

)

select
    '{{ var('season') }}' as season,
    * exclude (capture_rank)
from ranked
where capture_rank = 1
