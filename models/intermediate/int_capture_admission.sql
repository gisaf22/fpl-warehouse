-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_capture_admission
-- =============================================================================
--
-- Purpose:
--   Decides, for every indexed capture, whether the warehouse may read it
--   (#97; #87 decisions D1-D6). C2's staging reads only admitted captures.
--
-- Grain:
--   One row per base_capture_index row, keyed by capture_key.
--
-- Rule — admitted when all hold, otherwise the FIRST failing reason, in order:
--   run_not_finalized  the run has no finalized manifest (stg_run) and is not
--                      the history port, which has no manifest at all (D3).
--   origin_unknown     no origin from the manifest (2.2.0+) or the seed.
--                      stg_test_run_origin_seed_covers_every_pre_origin_run
--                      fails the build before this can be reached; the reason
--                      exists so nothing is ever admitted by default.
--   not_production     from 2.2.0, the manifest's origin is not ci on
--                      refs/heads/main (D1); before it, the seed is not ci or
--                      history_port (D2, D3). Run-level reasons come first, so
--                      a local run's captures read not_production whatever
--                      else is wrong with them (07eb06's seasons are null).
--   unusable           ingest's own usable = false.
--   null_season        no season: never guessed from a nearby run (D4).
--
-- flagged_revalidation:
--   An admitted capture whose shape verdict came from revalidation and failed
--   (shape_source = revalidated, shape_ok = false). Admitted until reviewed,
--   per the spec. Only a revalidated verdict is flagged.
-- =============================================================================

with joined as (

    select
        captures.capture_key,
        captures.run_id,
        captures.season,
        captures.usable,
        captures.shape_ok,
        captures.shape_source,
        runs.run_id is not null                    as has_finalized_manifest,
        runs.origin_kind                           as manifest_origin_kind,
        runs.origin_ref                            as manifest_origin_ref,
        seed.origin_kind                           as seed_origin_kind
    from {{ ref('base_capture_index') }} as captures
    left join {{ ref('stg_run') }} as runs
        on runs.run_id = captures.run_id
    left join {{ ref('seed_run_origin') }} as seed
        on seed.run_id = captures.run_id

),

reasoned as (

    select
        *,
        case
            when not has_finalized_manifest
                 and seed_origin_kind is distinct from 'history_port'
                then 'run_not_finalized'
            when manifest_origin_kind is null and seed_origin_kind is null
                then 'origin_unknown'
            when manifest_origin_kind is not null
                 and not (manifest_origin_kind = 'ci'
                          and manifest_origin_ref = 'refs/heads/main')
                then 'not_production'
            when manifest_origin_kind is null
                 and seed_origin_kind not in ('ci', 'history_port')
                then 'not_production'
            when usable is distinct from true
                then 'unusable'
            when season is null
                then 'null_season'
        end                                        as unadmitted_reason
    from joined

)

select
    capture_key,
    run_id,
    season,
    unadmitted_reason is null                      as admitted,
    unadmitted_reason is null
        and shape_source = 'revalidated'
        and shape_ok is false                      as flagged_revalidation,
    unadmitted_reason
from reasoned
