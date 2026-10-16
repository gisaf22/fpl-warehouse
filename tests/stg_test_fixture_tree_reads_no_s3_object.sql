-- Layer: stg
-- Tests: every fpl_raw source
-- Asserts: under the fixtures target, every object any source reads is a file
--          in the checked-in tree — none is an s3:// URL.
-- Origin: new in #36 — adding the fixtures endpoint adds a source, and each
--         source switches its own path on the target. This keeps the PR path
--         credential-free for all of them, not only the ones that existed when
--         the switch was written. CI's no-AWS_* guard is the other half.
--         element_summary is checked in scripts/tests/test_staging_reads_compacted.py
--         since #194: its source is built by a pre-hook on the model's own
--         connection, and its compacted rows carry production s3:// filenames
--         that were recorded, not read.
-- Tier: integration
{{ config(tags=['integration'], meta={'covers': '#36 AC4'}) }}

{% if target.name != 'fixtures' %}

select null as failure where false

{% else %}

with read_objects as (

    select 'bootstrap_static' as source_name, filename
    from {{ source('fpl_raw', 'bootstrap_static') }}
    union all
    select 'event_status', filename
    from {{ source('fpl_raw', 'event_status') }}
    union all
    select 'fixtures', filename
    from {{ source('fpl_raw', 'fixtures') }}
    union all
    select 'run_manifests', filename
    from {{ source('fpl_raw', 'run_manifests') }}
    union all
    select 'backfill_catalog', filename
    from {{ source('fpl_raw', 'backfill_catalog') }}

)

select distinct source_name, filename
from read_objects
where filename not like 'tests/fixtures/%'

{% endif %}
