-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_entry_picks
-- =============================================================================
--
-- Purpose:
--   One row per pick: stg_entry_picks_capture's `picks` unnested (#216).
--   Typing is done there; this model only flattens, so the source is read
--   once.
--
-- Grain:
--   One row per (capture_key, slot); 15 per capture.
-- =============================================================================

with captures as (

    select capture_key, season, entry_id, gameweek, unnest(picks) as pick
    from {{ ref('stg_entry_picks_capture') }}

)

select
    capture_key,
    season,
    entry_id,
    gameweek,
    pick.slot,
    pick.fpl_id,
    pick.multiplier,
    pick.is_captain,
    pick.is_vice_captain
from captures
