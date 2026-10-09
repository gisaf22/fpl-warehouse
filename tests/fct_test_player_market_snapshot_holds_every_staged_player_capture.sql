-- Layer: fct
-- Tests: fct_player_market_snapshot
-- Asserts: the snapshot holds exactly the (season, fpl_id, capture_key) keys
--          stg_player holds: none missing, none extra.
-- Origin: new in #141
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#141 AC1'}) }}

-- stg_player holds one row per player per admitted bootstrap-static capture
-- (#140 AC3), so its keys are the set the snapshot must reproduce. Uniqueness
-- is the generic test in schema.yml; this is completeness, both ways.

with staged as (
    select season, fpl_id, capture_key from {{ ref('stg_player') }}
),

snapshot as (
    select season, fpl_id, capture_key from {{ ref('fct_player_market_snapshot') }}
)

(select 'missing from snapshot' as problem, * from staged
 except select 'missing from snapshot', * from snapshot)
union all
(select 'not a staged player capture', * from snapshot
 except select 'not a staged player capture', * from staged)
