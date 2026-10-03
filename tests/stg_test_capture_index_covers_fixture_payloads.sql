-- Layer: stg
-- Tests: base_capture_index, capture_key_from_filename
-- Asserts: under the fixtures target, every payload in the checked-in trees
--          normalizes to a key that is in the capture index.
-- Origin: new in #95 (C1a of #87)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#95 AC3'}) }}

-- Fixture target only. Against live S3 a run still in progress when the build
-- starts has payloads but no finalized manifest, so the same check would fail
-- the scheduled build for no defect. C2 owns the live-side check.

{% if target.name != 'fixtures' %}

select null as filename where false

{% else %}

with payloads as (

    select file as filename
    from glob('tests/fixtures/raw/fpl/**/payload.json')
    union all
    select file
    from glob('tests/fixtures/history/*/fpl/**/payload.json')

)

select filename
from payloads
where {{ capture_key_from_filename('filename') }} not in (
    select capture_key from {{ ref('base_capture_index') }}
)

union all

select 'no payload found under tests/fixtures'
where not exists (select 1 from payloads)

{% endif %}
