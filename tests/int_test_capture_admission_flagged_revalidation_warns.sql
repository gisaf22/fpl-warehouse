-- Layer: int
-- Tests: int_capture_admission
-- Asserts: no admitted capture carries flagged_revalidation, a failed shape
--          revalidation admitted until someone reviews it (E4).
-- Origin: new in #104 (C2d of #88)
-- Tier: integration. Warn severity: the build passes and the warning names
--       each capture.
{{ config(group='warehouse_internal', tags=['integration'], severity='warn', meta={'covers': '#104 AC7'}) }}

select capture_key, run_id, season, 'admitted with a failed revalidation' as warning
from {{ ref('int_capture_admission') }}
where admitted and flagged_revalidation
