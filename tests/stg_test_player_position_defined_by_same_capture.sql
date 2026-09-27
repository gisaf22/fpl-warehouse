-- Layer: stg
-- Tests: stg_player, stg_position
-- Asserts: every staged player's position is one of the positions defined by
--          the same bootstrap-static capture.
-- Origin: new in #38
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#38 AC4'}) }}

-- Matched within the same (season, run_id), never across captures or seasons.
-- A null position matches nothing and fails too.

select
    player.season,
    player.run_id,
    player.fpl_id,
    player.position_id
from {{ ref('stg_player') }} as player
where not exists (
    select 1
    from {{ ref('stg_position') }} as position
    where position.season      = player.season
      and position.run_id      = player.run_id
      and position.position_id = player.position_id
)
