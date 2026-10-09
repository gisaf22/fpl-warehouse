-- Layer: stg
-- Tests: stg_player
-- Asserts: every stg_player row carries the total_players of its own
--          capture's root, never null and never another capture's.
-- Origin: new in #140
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#140 AC1'}) }}

-- The root is read again here, on its own, through the same declared read
-- staging uses, and compared per capture_key against what each player row
-- carries. A wrong join (another capture's root, a fan-out, a lost root)
-- shows up as a row here.

with root as (
    {{ declared_records('bootstrap_static', '$') }}
)

select
    player.capture_key,
    player.fpl_id,
    player.total_players as staged,
    root.total_players   as published
from {{ ref('stg_player') }} as player
left join root
    on root.capture_key = player.capture_key
where player.total_players is null
   or player.total_players is distinct from root.total_players
