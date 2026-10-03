-- Layer: stg
-- Tests: stg_run
-- Asserts: origin_kind is set for every run on a contract that records origin
--          (2.2.0 and later) and null for every run on an earlier one, and the
--          run's start and end are timestamps.
-- Origin: new in #95 (C1a of #87)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#95 AC4'}) }}

-- The versions before origin existed are listed rather than compared as
-- strings, so '2.10.0' could never sort below '2.2.0'.

select
    run_id,
    raw_contract_version,
    origin_kind,
    typeof(run_started_at) as started_type,
    typeof(run_ended_at)   as ended_type
from {{ ref('stg_run') }}
where (origin_kind is null) <> (raw_contract_version in ('1.0.0', '1.1.0', '2.0.0', '2.1.0'))
   or typeof(run_started_at) <> 'TIMESTAMP'
   or typeof(run_ended_at)   <> 'TIMESTAMP'
