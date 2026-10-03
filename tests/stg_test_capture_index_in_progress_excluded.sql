-- Layer: stg
-- Tests: stg_run, base_capture_index
-- Asserts: a run whose manifest is IN_PROGRESS is in neither stg_run nor the
--          capture index.
-- Origin: new in #95 (C1a of #87)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#95 AC2'}) }}

-- The fixture tree carries one synthetic IN_PROGRESS manifest (IN_PROGRESS_RUN
-- in tests/fixtures/build_fixtures.py). Live S3 has never held one (measured
-- 2026-10-03), so against dev this normally checks an empty set.

with in_progress as (

    select run_id
    from {{ source('fpl_raw', 'run_manifests') }}
    where status = 'IN_PROGRESS'

)

select run_id, 'in stg_run' as failure
from in_progress
where run_id in (select run_id from {{ ref('stg_run') }})

union all

select run_id, 'in base_capture_index'
from in_progress
where run_id in (select run_id from {{ ref('base_capture_index') }})
