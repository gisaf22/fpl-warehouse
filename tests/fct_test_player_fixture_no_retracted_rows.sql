{{ config(group='warehouse_internal') }}
-- Group membership is required, not cosmetic: this test ref()s
-- stg_player_fixture, which is access: private to warehouse_internal.
-- Without it dbt refuses to parse the test. See CLAUDE.md, "Served contract".

-- fct_player_fixture must not carry a (fpl_id, fixture_id) that FPL has since
-- removed from the player's history.
--
-- Staging accumulates every capture ever taken, so a row FPL published once and
-- later deleted survives there permanently. Carried into the fact it becomes a
-- fixture the player never played, inflating fixture_count — a gameweek reported
-- as a double that was not one. Observed for two mid-season transfers on
-- 2026-09-03, where each player briefly carried a row for their other club's
-- fixture.
--
-- The ratified-preference rule does not cover this: one of those ghost rows was
-- itself ratified.

with latest_run_per_player as (

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
        from (select distinct fpl_id, run_id, extracted_at from {{ ref('stg_player_fixture') }})
    )
    where run_rank = 1

),

current_keys as (

    select distinct
        stg.fpl_id,
        stg.fixture_id
    from {{ ref('stg_player_fixture') }} as stg
    inner join latest_run_per_player using (fpl_id, run_id)

)

select
    fct.fpl_id,
    fct.fixture_id,
    fct.round
from {{ ref('fct_player_fixture') }} as fct
left join current_keys using (fpl_id, fixture_id)
where current_keys.fpl_id is null
