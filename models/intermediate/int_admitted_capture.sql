-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_admitted_capture
-- =============================================================================
--
-- Purpose:
--   Every admitted capture with its metadata, which is what every payload
--   staging model joins to (#104; #88 E1, E7). Staging keeps a payload only
--   when its key is here, and takes its capture columns from here rather than
--   from the object's path.
--
-- Grain:
--   One row per admitted capture, keyed by capture_key.
--
-- Columns:
--   season, run_id     from the capture index.
--   observed_at        the index's received_at. Every "latest capture wins"
--                      ordering uses it, with run_id breaking a tie.
--   extraction_date    the run manifest's (stg_run). The history port has no
--                      manifest, so its is received_at's date.
--   extracted_at       the run's start to the second (stg_run.run_started_at),
--                      or received_at for the history port, whose catalog
--                      records its run instant there (fpl-ingest#66 AC6).
--                      Kept only because fct_player_fixture serves it (E1);
--                      nothing orders by it.
--   Both served columns equal what parsing the object key used to give: the
--   run_id instant matched the run start for 199 of 199 runs, and the key's
--   date the manifest's for 198 of 198 (#88 step 0).
--
-- Not here, so excluded silently (E7):
--   an unadmitted capture (int_capture_admission says why), and a payload
--   with no index entry, typically one whose run was still in progress at
--   build time. It is picked up by the next build.
-- =============================================================================

select
    captures.capture_key,
    captures.season,
    captures.run_id,
    coalesce(runs.extraction_date, cast(captures.received_at as date))
                                                   as extraction_date,
    coalesce(
        date_trunc('second', runs.run_started_at),
        date_trunc('second', captures.received_at)
    )                                              as extracted_at,
    captures.received_at                           as observed_at
from {{ ref('base_capture_index') }} as captures
inner join {{ ref('int_capture_admission') }} as admission
    on admission.capture_key = captures.capture_key
left join {{ ref('stg_run') }} as runs
    on runs.run_id = captures.run_id
where admission.admitted
