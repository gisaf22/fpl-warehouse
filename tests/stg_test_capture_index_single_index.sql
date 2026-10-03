-- Layer: stg
-- Tests: base_capture_index
-- Asserts: no run's captures come from both a manifest and the catalog — each
--          run, and so each key, is indexed exactly once.
-- Origin: new in #95 (C1a of #87)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#95 AC1'}) }}

-- Key uniqueness across both halves is the generic unique test on capture_key.
-- This is the run-level half: a run indexed by both sources would double every
-- key it holds if the two lists agreed, and split its captures between two
-- sources of truth if they did not.

select
    run_id,
    count(distinct index_source) as index_sources
from {{ ref('base_capture_index') }}
group by run_id
having count(distinct index_source) > 1
