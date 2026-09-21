-- Layer: stg
-- Tests: stg_player, stg_player_fixture
-- Asserts: in every settled run, each player's bootstrap-static total_points
--          equals the sum of total_points over the same run's element-summary
--          history for that player.
-- Origin: new in the 2025-26 history port, Step 1 — the permanent form of the
--         2026-09-16 full-population check
-- Tier: e2e
{{ config(group='warehouse_internal', tags=['e2e']) }}

-- Group membership is required, not cosmetic: this test ref()s stg_player,
-- stg_player_fixture and stg_gameweek, all access: private to
-- warehouse_internal.

-- Why "same run": bootstrap-static and element-summary are separate captures,
-- and the live cron no longer takes element-summary at all, so a player's
-- latest bootstrap is routinely newer than their latest history. Only captures
-- sharing a run_id describe the same moment.
--
-- Why "settled": a run is one process, but its bootstrap-static and
-- element-summary requests are still seconds to minutes apart. On a match day
-- points move in between. Measured 2026-09-16 over the live tree: 158 of
-- 47,793 same-run pairs disagreed, every one in a run whose current round was
-- not yet data_checked; across the 18 runs where it was, 0 of 1,280 disagreed.
-- A run counts as settled when its own calendar reports the current round
-- data_checked — the run's own statement, not a later one.
--
-- Why e2e: the checked-in fixture tree holds no settled run, so this test
-- would pass vacuously under `--target fixtures`, and it carries a synthetic
-- double-gameweek row (player 233, fixture 999) that deliberately does not
-- touch bootstrap totals. Only the live tree exercises it.
--
-- Staging, not the served table, is compared on purpose: both sides here are
-- one run's raw statement, with no dedup in between to mask a disagreement.
-- A player whose same-run history is empty has no stg_player_fixture rows and
-- is not compared.

with settled_runs as (

    select season, run_id
    from {{ ref('stg_gameweek') }}
    group by season, run_id
    having bool_and(not is_current or data_checked)

),

history_totals as (

    select
        history.season,
        history.run_id,
        history.fpl_id,
        sum(history.total_points) as history_total_points
    from {{ ref('stg_player_fixture') }} as history
    inner join settled_runs using (season, run_id)
    group by history.season, history.run_id, history.fpl_id

),

compared as (

    select
        player.season,
        player.run_id,
        player.fpl_id,
        player.total_points,
        history_totals.history_total_points
    from {{ ref('stg_player') }} as player
    inner join history_totals
        on history_totals.season = player.season
       and history_totals.run_id = player.run_id
       and history_totals.fpl_id = player.fpl_id

)

select
    'total_points disagrees with same-run history' as failure,
    season,
    run_id,
    fpl_id,
    total_points,
    history_total_points
from compared
where total_points is distinct from history_total_points

union all

-- Guard against a vacuous pass: with no settled run, or no player captured in
-- one, `compared` is empty and the check above proves nothing.
select
    'no settled same-run pair to compare' as failure,
    null, null, null, null, null
from (select count(*) as pairs from compared)
where pairs = 0
