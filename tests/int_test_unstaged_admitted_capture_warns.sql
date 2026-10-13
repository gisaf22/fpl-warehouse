-- Layer: int
-- Tests: int_unstaged_admitted_capture
-- Asserts: no admitted capture of a warn-only endpoint lacks a staging row
--          (#167 G6). Warn severity: the build passes, and the scheduled
--          build's job summary names each capture.
-- Origin: new in #167
-- Tier: integration. On the fixture tree it warns on fpl_id 9999's capture.
{{ config(group='warehouse_internal', tags=['integration'], severity='warn', meta={'covers': '#167 AC1'}) }}

select endpoint, season, run_id, capture_key, observed_at
from {{ ref('int_unstaged_admitted_capture') }}
where severity = 'warn'
