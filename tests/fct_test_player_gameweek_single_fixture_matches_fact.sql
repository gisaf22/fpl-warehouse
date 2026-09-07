-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: where a round holds exactly one fixture, the aggregate reproduces that
--          fixture's values verbatim — aggregation is the identity on one row.
-- Origin: new in Phase 2
-- Tier: integration
{{ config(tags=['integration']) }}

-- Where a gameweek holds exactly one fixture, the aggregate must reproduce that
-- fixture's values verbatim. Aggregation is only meant to combine fixtures, so
-- with one fixture it must be the identity.
--
-- This is the regression guard for ict_index in particular. Recomputing it as
-- (influence + creativity + threat) / 10 rather than summing the published
-- index silently altered 31 of 1,236 rows, because FPL publishes some rows
-- whose index does not reconcile with its own components.

select
    agg.season,
    agg.fpl_id,
    agg.round,
    agg.total_points,
    fct.total_points as fct_total_points,
    agg.ict_index,
    fct.ict_index    as fct_ict_index
from {{ ref('fct_player_gameweek') }} as agg
inner join {{ ref('fct_player_fixture') }} as fct using (season, fpl_id, round)
where agg.fixture_count = 1
  and (
        agg.minutes      <> fct.minutes
     or agg.total_points <> fct.total_points
     or agg.bonus        <> fct.bonus
     or agg.bps          <> fct.bps
     or agg.goals_scored <> fct.goals_scored
     or agg.assists      <> fct.assists
     or abs(agg.ict_index  - fct.ict_index)  > 0.0001
     or abs(agg.influence  - fct.influence)  > 0.0001
     or abs(agg.creativity - fct.creativity) > 0.0001
     or abs(agg.threat     - fct.threat)     > 0.0001
  )
