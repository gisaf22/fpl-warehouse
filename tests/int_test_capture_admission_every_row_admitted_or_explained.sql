-- Layer: int
-- Tests: int_capture_admission
-- Asserts: every indexed capture appears once, and exactly one of admitted and
--          a non-null unadmitted_reason holds for it.
-- Origin: new in #97 (C1c of #87)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#97 AC5'}) }}

select capture_key, admitted, unadmitted_reason, 'admitted and explained alike' as failure
from {{ ref('int_capture_admission') }}
where admitted = (unadmitted_reason is not null)
   or admitted is null

union all

select capture_key, null, null, 'indexed capture missing from admission'
from {{ ref('base_capture_index') }}
where capture_key not in (
    select capture_key from {{ ref('int_capture_admission') }}
)
