-- Layer: stg
-- Tests: capture_key_from_filename (macro)
-- Asserts: every object-key layout a build can read normalizes to its index
--          key — raw/fpl/... for the live tree, history/<season>/fpl/... for a
--          ported season — whatever root it was read from.
-- Origin: new in #95 (C1a of #87)
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#95 AC3'}) }}

with cases (object_path, expected) as (

    values
        -- dev, live tree
        ('s3://fpl-data-safari/raw/fpl/element-summary/1/2026-09-15/20260915T191327Z-6b4127/payload.json',
         'raw/fpl/element-summary/1/2026-09-15/20260915T191327Z-6b4127/payload.json'),
        -- dev, history tree
        ('s3://fpl-data-safari/history/2025-26/fpl/bootstrap-static/2026-05-26/20260526T034626Z-2a6b73/payload.json',
         'history/2025-26/fpl/bootstrap-static/2026-05-26/20260526T034626Z-2a6b73/payload.json'),
        -- dev with a local raw_root override
        ('.local/raw/fpl/fixtures/2026-09-14/20260914T211204Z-a730c3/payload.json',
         'raw/fpl/fixtures/2026-09-14/20260914T211204Z-a730c3/payload.json'),
        -- an absolute local root whose own path mentions fpl
        ('/Users/someone/fpl-warehouse/.local/raw/fpl/event-status/2026-09-02/20260902T071919Z-34bc3a/payload.json',
         'raw/fpl/event-status/2026-09-02/20260902T071919Z-34bc3a/payload.json'),
        -- fixtures target, live tree
        ('tests/fixtures/raw/fpl/element-summary/426/2026-08-29/20260829T191108Z-b12d19/payload.json',
         'raw/fpl/element-summary/426/2026-08-29/20260829T191108Z-b12d19/payload.json'),
        -- fixtures target, history tree
        ('tests/fixtures/history/2025-26/fpl/element-summary/1/2026-05-26/20260526T034626Z-2a6b73/payload.json',
         'history/2025-26/fpl/element-summary/1/2026-05-26/20260526T034626Z-2a6b73/payload.json')

)

select
    object_path,
    expected,
    {{ capture_key_from_filename('object_path') }} as actual
from cases
where {{ capture_key_from_filename('object_path') }} is distinct from expected
