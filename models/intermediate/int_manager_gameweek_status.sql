-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_manager_gameweek_status
-- =============================================================================
--
-- Purpose:
--   The audit grid (#216 D1, D5): one row per panel manager per marked
--   gameweek, with its status and, when captured, the winning capture. The
--   served tables take their rows from the `captured` ones.
--
-- Status (GLOSSARY.md, manager-gameweek status):
--   not_yet_joined      before the join week, or the manager has no join week
--   captured            an admitted picks capture exists
--   missing_after_join  neither; fails the build (AC3)
--
-- Which capture wins:
--   The latest observed_at, run_id breaking a tie, as for element-summary.
--   A settled gameweek's picks are captured once, so two captures of one
--   manager-gameweek come only from a rerun.
--
-- An unmarked gameweek has no row (D4): it is not settled.
-- =============================================================================

with winning as (

    select season, entry_id, gameweek, capture_key
    from {{ ref('stg_entry_picks_capture') }}
    qualify row_number() over (
        partition by season, entry_id, gameweek
        order by observed_at desc, run_id desc
    ) = 1

),

grid as (

    select
        panel.season,
        panel.entry_id,
        markers.gameweek,
        panel.first_active_gw,
        winning.capture_key,
        case
            when panel.first_active_gw is null
              or markers.gameweek < panel.first_active_gw then 'not_yet_joined'
            when winning.capture_key is not null         then 'captured'
            else 'missing_after_join'
        end as status
    from {{ ref('dim_manager_panel') }} as panel
    inner join {{ ref('stg_entry_picks_settlement') }} as markers
        on markers.season = panel.season
    left join winning
        on winning.season = panel.season
       and winning.entry_id = panel.entry_id
       and winning.gameweek = markers.gameweek

)

select
    season,
    entry_id,
    gameweek,
    first_active_gw,
    case when status = 'captured' then capture_key end as capture_key,
    status
from grid
