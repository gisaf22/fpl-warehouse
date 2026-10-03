-- Layer: stg
-- Tests: seed_run_origin, stg_run, base_capture_index
-- Asserts: every run whose origin the manifest does not record has a seed row,
--          and every run on a contract that records origin does record it — a
--          run with unknown origin fails the build, named.
-- Origin: new in #96 (C1b of #87, decision D7)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#96 AC3'}) }}

-- Pre-origin runs are the indexed runs with no origin_kind in stg_run: every
-- run on a contract before 2.2.0, and the history port, which has no manifest
-- and so no stg_run row. Without this, a run missing from the seed would read
-- as unknown and admission (#97) would silently drop all of its captures.

with indexed_runs as (

    select distinct run_id
    from {{ ref('base_capture_index') }}

),

pre_origin as (

    select indexed_runs.run_id
    from indexed_runs
    left join {{ ref('stg_run') }} as runs
        on runs.run_id = indexed_runs.run_id
    where runs.origin_kind is null

)

select run_id, 'no seed_run_origin row' as failure
from pre_origin
where run_id not in (select run_id from {{ ref('seed_run_origin') }})

union all

select run_id, 'contract ' || raw_contract_version || ' records no origin'
from {{ ref('stg_run') }}
where origin_kind is null
  and raw_contract_version not in ('1.0.0', '1.1.0', '2.0.0', '2.1.0')
