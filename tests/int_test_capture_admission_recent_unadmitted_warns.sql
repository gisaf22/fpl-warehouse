-- Layer: int
-- Tests: int_capture_admission
-- Asserts: no capture from a run started in the last 7 days is unadmitted (E4).
--          Older exclusions, such as 07eb06's 651 local captures, are settled
--          and would only warn forever.
-- Origin: new in #104 (C2d of #88)
-- Tier: integration. Warn severity: the build passes and the warning names
--       each capture and its reason.
--
-- A run's start is stg_run's run_started_at, or the capture's received_at for
-- a run with no finalized manifest. "Now" is the freshness_as_of var when set,
-- as in int_endpoint_freshness, else the current UTC time.
{{ config(group='warehouse_internal', tags=['integration'], severity='warn', meta={'covers': '#104 AC7'}) }}

select admission.capture_key, admission.run_id, admission.unadmitted_reason,
       coalesce(runs.run_started_at, captures.received_at) as run_started_at
from {{ ref('int_capture_admission') }} as admission
inner join {{ ref('base_capture_index') }} as captures
    on captures.capture_key = admission.capture_key
left join {{ ref('stg_run') }} as runs
    on runs.run_id = admission.run_id
where not admission.admitted
  and coalesce(runs.run_started_at, captures.received_at)
      >= {{ as_of_utc() }} - interval 7 day
