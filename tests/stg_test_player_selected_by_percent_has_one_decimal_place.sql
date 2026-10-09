-- Layer: stg
-- Tests: stg_player
-- Asserts: no admitted capture publishes a selected_by_percent with more than
--          one decimal place, so staging's DECIMAL(4,1) cast is lossless.
-- Origin: new in #140 (D2)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], severity='error', meta={'covers': '#140 AC2'}) }}

-- The cast in stg_player rounds a value with more places without complaint, so
-- the published string is checked here, before the cast. Every value observed
-- up to 2026-10-09 has exactly one place. A failure names the capture, the
-- player and the value; widen the type before letting it through. Reads the
-- source's element records, restricted to the captures staging admits.

with records as (
    {{ declared_records('bootstrap_static', '$.elements[*]') }}
)

select
    records.capture_key,
    records."id"                  as fpl_id,
    records."selected_by_percent" as selected_by_percent
from records
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = records.capture_key
where regexp_matches(cast(records."selected_by_percent" as varchar), '\.[0-9]{2,}')
