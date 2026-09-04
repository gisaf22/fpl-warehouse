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
--   dbt_tests/fct_test_player_fixture_grain_uniqueness.sql.
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
--     1. ratified (both scores non-NULL) over provisional;
--     2. within that, the most recent capture.
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
--   the typing — plus `is_ratified`, false when even the surviving capture is
--   still provisional because no ratified one exists yet (a round
--   mid-settlement). Consumers wanting settled data only should filter on it
--   rather than re-deriving it from the scores.
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
        captures.team_h_score is not null
            and captures.team_a_score is not null            as is_ratified,
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

)

select
    '{{ var('season') }}' as season,
    * exclude (capture_rank)
from ranked
where capture_rank = 1
