-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_run
-- =============================================================================
--
-- Purpose:
--   One row per finalized fpl-ingest run, from its manifest (#95). Typing and
--   renaming only.
--
-- Finalized:
--   Any status other than IN_PROGRESS. A manifest left IN_PROGRESS belongs to
--   a run that is still writing or that crashed, and none of its captures may
--   be read. This model is the one place that rule lives: base_capture_index
--   takes its manifest captures only from runs listed here.
--
-- origin_*:
--   The manifest's `origin` object, recorded from contract 2.2.0
--   (gisaf22/fpl-ingest#75). Null for every older run, whose origin comes from
--   the run-origin seed instead (#96).
--
-- extraction_date:
--   The manifest's own date, which equalled the date directory in the run's
--   object keys for 198 of 198 manifests (#88 step 0). Served on
--   fct_player_fixture via int_admitted_capture (#104, #88 E1).
-- =============================================================================

select
    run_id,
    cast(extraction_date as date)  as extraction_date,
    cast(started_at as timestamp)  as run_started_at,
    cast(ended_at as timestamp)    as run_ended_at,
    status,
    trigger,
    raw_contract_version,
    origin.kind                    as origin_kind,
    origin.ref                     as origin_ref,
    origin.workflow                as origin_workflow,
    origin.github_run_id           as origin_github_run_id,
    origin.aws_principal           as origin_aws_principal

from {{ source('fpl_raw', 'run_manifests') }}
where status <> 'IN_PROGRESS'
