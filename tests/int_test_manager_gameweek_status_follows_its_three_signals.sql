-- Layer: int
-- Tests: int_manager_gameweek_status
-- Asserts: every panel manager has exactly one row per marked gameweek, whose
--          status follows the join week, an admitted picks capture and the
--          marker: not_yet_joined before the join week, else captured, else
--          missing_after_join; and the fixture holds both a not_yet_joined and
--          a captured row, so the check is not vacuous.
-- Origin: new in #216 (D1, D5)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC1'}) }}

with join_weeks as (

    select season, entry_id, min(gameweek) as first_active_gw
    from {{ ref('stg_entry_history') }}
    group by season, entry_id

),

expected as (

    select
        panel.season,
        panel.entry_id,
        markers.gameweek,
        case
            when markers.gameweek < join_weeks.first_active_gw then 'not_yet_joined'
            when exists (
                select 1
                from {{ ref('stg_entry_picks_capture') }} as captures
                where captures.season = panel.season
                  and captures.entry_id = panel.entry_id
                  and captures.gameweek = markers.gameweek
            ) then 'captured'
            else 'missing_after_join'
        end as status
    from {{ ref('stg_manager_panel') }} as panel
    inner join {{ ref('stg_entry_picks_settlement') }} as markers
        on markers.season = panel.season
    left join join_weeks
        on join_weeks.season = panel.season
       and join_weeks.entry_id = panel.entry_id

),

actual as (

    select season, entry_id, gameweek, status
    from {{ ref('int_manager_gameweek_status') }}

)

select
    coalesce(expected.season, actual.season)     as season,
    coalesce(expected.entry_id, actual.entry_id) as entry_id,
    coalesce(expected.gameweek, actual.gameweek) as gameweek,
    expected.status                              as expected_status,
    actual.status                                as actual_status
from expected
full outer join actual
    on actual.season = expected.season
   and actual.entry_id = expected.entry_id
   and actual.gameweek = expected.gameweek
where expected.status is distinct from actual.status

{% if target.name == 'fixtures' %}
union all
select null, null, null, required, 'absent from the fixture build'
from (values ('not_yet_joined'), ('captured')) as t(required)
where required not in (select status from actual)
{% endif %}
