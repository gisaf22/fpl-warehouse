-- Layer: stg
-- Tests: stg_player_fixture, stg_player, stg_position, stg_team, stg_gameweek,
--        stg_fixture, stg_gameweek_status
-- Asserts: each staging model holds exactly the admitted captures of its
--          endpoint, counted by distinct capture_key. stg_player_fixture is
--          held to at most: an element-summary payload whose history array is
--          empty (a player yet to play) yields no row, so it can be admitted
--          and absent.
-- Origin: new in #104 (C2d of #88)
-- Tier: e2e (the live tree, where the counts are the real ones)
{{ config(group='warehouse_internal', tags=['e2e'], meta={'covers': '#104 AC9'}) }}

with admitted as (
    select split_part(captures.endpoint, '/', 1) as endpoint,
           count(*) as admitted_captures
    from {{ ref('int_admitted_capture') }} as admitted
    inner join {{ ref('base_capture_index') }} as captures
        on captures.capture_key = admitted.capture_key
    group by 1
),

staged as (
    {% for model, endpoint in [('stg_player_fixture', 'element-summary'), ('stg_player', 'bootstrap-static'),
                               ('stg_position', 'bootstrap-static'), ('stg_team', 'bootstrap-static'),
                               ('stg_gameweek', 'bootstrap-static'), ('stg_fixture', 'fixtures'),
                               ('stg_gameweek_status', 'event-status')] %}
    select '{{ model }}' as model, '{{ endpoint }}' as endpoint,
           count(distinct capture_key) as staged_captures
    from {{ ref(model) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select staged.model, staged.endpoint, staged.staged_captures,
       coalesce(admitted.admitted_captures, 0) as admitted_captures
from staged
left join admitted on admitted.endpoint = staged.endpoint
where (staged.model = 'stg_player_fixture' and staged.staged_captures > coalesce(admitted.admitted_captures, 0))
   or (staged.model <> 'stg_player_fixture' and staged.staged_captures <> coalesce(admitted.admitted_captures, 0))
