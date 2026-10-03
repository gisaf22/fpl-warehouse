-- =============================================================================
-- Layer: base_ (staging)
-- Model: base_capture_index
-- =============================================================================
--
-- Purpose:
--   One row per capture ingest has indexed (#95): the single list of what
--   exists in the raw tree, for admission (#97) and for staging's reads (C2).
--   No admission logic here.
--
-- Two indexes, disjoint by run:
--   manifest  `captures[]` of every finalized manifest that carries it —
--             contract 2.1.0 and later. Finalized is stg_run's rule.
--   catalog   the backfill catalog, for every older run and for the ported
--             history season (`scope` = history).
--   Measured 2026-10-03: no run and no key is in both.
--   stg_test_capture_index_single_index holds that.
--
-- Columns ingest records only in the catalog (`scope`, `shape_source`,
-- `validator_version`) are null for manifest captures.
-- =============================================================================

with manifest_captures as (

    select
        manifests.run_id,
        unnest(manifests.captures) as capture
    from {{ source('fpl_raw', 'run_manifests') }} as manifests
    inner join {{ ref('stg_run') }} as runs
        on runs.run_id = manifests.run_id
    where manifests.captures is not null

),

catalog_captures as (

    select
        run_id,
        scope,
        unnest(captures) as capture
    from {{ source('fpl_raw', 'backfill_catalog') }}

),

indexed as (

    select
        run_id,
        'manifest'                         as index_source,
        cast(null as varchar)              as scope,
        capture.key                        as capture_key,
        capture.endpoint                   as endpoint,
        capture.received_at                as received_at,
        capture.content_sha256             as content_sha256,
        capture.content_length             as content_length,
        capture.http_status                as http_status,
        capture.shape_ok                   as shape_ok,
        capture.usable                     as usable,
        capture.season                     as season,
        cast(null as varchar)              as shape_source,
        cast(null as varchar)              as validator_version
    from manifest_captures

    union all

    select
        run_id,
        'catalog',
        scope,
        capture.key,
        capture.endpoint,
        capture.received_at,
        capture.content_sha256,
        capture.content_length,
        capture.http_status,
        capture.shape_ok,
        capture.usable,
        capture.season,
        capture.shape_source,
        capture.validator_version
    from catalog_captures

)

select
    capture_key,
    run_id,
    index_source,
    scope,
    endpoint,
    cast(received_at as timestamp)         as received_at,
    content_sha256,
    content_length,
    http_status,
    shape_ok,
    usable,
    season,
    shape_source,
    validator_version
from indexed
