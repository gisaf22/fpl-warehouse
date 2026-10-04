-- Layer: int
-- Tests: int_endpoint_freshness
-- Asserts: no live endpoint's newest admitted capture is over 6h old.
--          element-summary is exempt. Warn severity: a missed ingest run
--          annotates the scheduled build but does not stop it.
-- Origin: new in #103 (C2c of #88), replacing #39's source freshness warn_after
-- Tier: e2e (live only: the fixture tree is old by construction)
{{ config(group='warehouse_internal', tags=['e2e'], severity='warn', meta={'covers': '#103 AC3'}) }}

select endpoint, newest_received_at, age_hours, freshness_status
from {{ ref('int_endpoint_freshness') }}
where freshness_status in ('warn', 'error')
