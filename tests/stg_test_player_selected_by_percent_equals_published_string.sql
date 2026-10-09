-- Layer: stg
-- Tests: stg_player
-- Asserts: every staged selected_by_percent equals the string FPL published
--          for that player in that capture, with no rounding loss; an empty
--          string is staged as NULL.
-- Origin: new in #140
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#140 AC2'}) }}

-- The value check a dbt unit test cannot make: it casts its expected rows to
-- the model's column type, so a narrower type (DECIMAL(4,0)) would round 31.2
-- to 31 on both sides and pass. Here the staged decimal is compared with the
-- published string as numbers of the source's own precision. Reads the
-- source's element records for the captures staging admits.

with records as (
    {{ declared_records('bootstrap_static', '$.elements[*]') }}
)

select
    player.capture_key,
    player.fpl_id,
    records."selected_by_percent" as published,
    player.selected_by_percent    as staged
from {{ ref('stg_player') }} as player
inner join records
    on  records.capture_key = player.capture_key
    and cast(records."id" as integer) = player.fpl_id
where player.selected_by_percent is distinct from
      cast(nullif(cast(records."selected_by_percent" as varchar), '') as decimal(18, 9))
