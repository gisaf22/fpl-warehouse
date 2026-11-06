-- Layer: stg
-- Tests: stg_player_history_capture
-- Asserts: no declared history field is typed JSON, even when a compacted day
--          holds only a capture with an empty history, and that capture is
--          staged with history_count 0 (#225 AC1).
-- Origin: new in #225
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#225 AC1'}) }}

-- fpl_id 655's capture in 20260910T191141Z-9d8de9 is the only capture of
-- 2026-09-10, and FPL returned its history empty: the player was added that run
-- and had not played. The day's parquet therefore infers history as JSON[]
-- (production's, trimmed into tests/fixtures/compacted). Read with the other
-- days' typed history in one union, it widened every day's fields to JSON, and
-- the scheduled build ran out of memory (#225). Live holds the same capture.

{% set key = 'raw/fpl/element-summary/655/2026-09-10/20260910T191141Z-9d8de9/payload.json' %}

select 'history is typed ' || history_type as problem
from (select distinct typeof("history") as history_type from {{ ref('stg_player_history_capture') }})
where history_type like '%JSON%'
union all
select 'the empty-history capture is not staged with history_count 0'
where not exists (
    select 1 from {{ ref('stg_player_history_capture') }}
    where capture_key = '{{ key }}' and history_count = 0
)
