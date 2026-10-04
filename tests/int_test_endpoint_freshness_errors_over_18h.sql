-- Layer: int
-- Tests: int_endpoint_freshness
-- Asserts: no live endpoint's newest admitted capture is over 18h old, and
--          none has no admitted capture at all. element-summary is exempt.
--          Error severity: the scheduled build stops before `dbt build` and
--          the publish.
-- Origin: new in #103 (C2c of #88), replacing #39's source freshness error_after
-- Tier: e2e (live only: the fixture tree is old by construction)
{{ config(group='warehouse_internal', tags=['e2e'], meta={'covers': '#103 AC3'}) }}

select endpoint, newest_received_at, age_hours, freshness_status
from {{ ref('int_endpoint_freshness') }}
where freshness_status = 'error'
