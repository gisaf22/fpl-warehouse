-- Layer: int
-- Tests: int_unstaged_admitted_capture
-- Asserts: every admitted capture of a fail-hard endpoint has a row in one of
--          its endpoint's staging models (#167 G1, G2, G6). Error severity:
--          the build fails, and the scheduled build's job summary names each
--          capture.
-- Origin: new in #167
-- Tier: e2e (live only: the fixture tree keeps two such gaps on purpose, G4)
{{ config(group='warehouse_internal', tags=['e2e'], meta={'covers': '#167 AC1'}) }}

select endpoint, season, run_id, capture_key, observed_at
from {{ ref('int_unstaged_admitted_capture') }}
where severity = 'error'
