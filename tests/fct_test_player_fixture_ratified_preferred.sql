{{ config(group='warehouse_internal') }}
-- Group membership is required, not cosmetic: this test ref()s
-- stg_player_fixture, which is access: private to warehouse_internal.
-- Without it dbt refuses to parse the test. See CLAUDE.md, "Served contract".

-- Dedup must never keep a provisional capture when a ratified one exists for
-- the same key.
--
-- A provisional capture (taken before the round settled) has NULL
-- team_h_score / team_a_score and carries "0.0" in the whole ICT family. The
-- NULL scores are the visible marker; the zeroed stats ride along silently, so
-- this assertion is the guard against reintroducing that corruption class.
--
-- Fails with one row per key where fct kept a NULL-score capture even though
-- staging held a scored one.

with ratified_available as (

    select distinct
        fpl_id,
        fixture_id
    from {{ ref('stg_player_fixture') }}
    where team_h_score is not null
      and team_a_score is not null

)

select
    fct.fpl_id,
    fct.fixture_id,
    fct.run_id
from {{ ref('fct_player_fixture') }} as fct
inner join ratified_available using (fpl_id, fixture_id)
where fct.team_h_score is null
   or fct.team_a_score is null
