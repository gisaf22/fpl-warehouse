-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: a gameweek ratified in event-status serves the ranked_count of the
--          first staged bootstrap-static capture at or after its
--          ratification. Ratification is the first event-status capture in
--          which every dated entry for the gameweek is points = 'r' with
--          bonus_added (int_gameweek_status, rule 1).
-- Origin: new in #219 (D2). In the fixture GW2 is ratified at 09-02 07:19, so
--         its reference is the 09-06 capture's 9,904,815; the captures before
--         ratification read 9,907,576 and 9,905,833. On the fixture the newest
--         capture and the reference agree by construction: a value that moves
--         after ratification has never been observed, and can only show up
--         live.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#219 AC4'}) }}

with ratifying_capture as (

    select season, gameweek, observed_at, run_id
    from {{ ref('stg_gameweek_status') }}
    group by season, gameweek, observed_at, run_id
    having bool_and(points = 'r' and bonus_added)

),

ratified_at as (

    select season, gameweek, min(observed_at) as ratified_at
    from ratifying_capture
    group by season, gameweek

),

reference as (

    select
        ratified_at.season,
        ratified_at.gameweek,
        ratified_at.ratified_at,
        captures.ranked_count,
        captures.capture_key
    from ratified_at
    left join {{ ref('stg_gameweek') }} as captures
        on captures.season = ratified_at.season
       and captures.gameweek = ratified_at.gameweek
       and captures.observed_at >= ratified_at.ratified_at
    qualify row_number() over (
        partition by ratified_at.season, ratified_at.gameweek
        order by captures.observed_at, captures.run_id
    ) = 1

)

select
    reference.season,
    reference.gameweek,
    reference.ratified_at,
    reference.capture_key         as reference_capture_key,
    reference.ranked_count        as reference_ranked_count,
    served.ranked_count           as served_ranked_count
from reference
left join {{ ref('dim_gameweek') }} as served
    on served.season = reference.season
   and served.gameweek = reference.gameweek
where served.ranked_count is distinct from reference.ranked_count

{% if target.name == 'fixtures' %}
union all
select 'no gameweek ratified in event-status in the fixture', null, null, null, null, null
where not exists (select 1 from reference)
{% endif %}
