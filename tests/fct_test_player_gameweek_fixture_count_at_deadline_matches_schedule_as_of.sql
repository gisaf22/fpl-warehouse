-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: wherever fixture_count_at_deadline is knowable, it equals the
--          number of fixtures the player's club had in that gameweek in the
--          served schedule as of the deadline, with the club also as of the
--          deadline.
-- Origin: new in #221 (D2)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#221 AC3'}) }}

-- The oracle is ADR 0002's consumer join, written out as range predicates on
-- dim_fixture_schedule_history and dim_player_status_history (valid_from
-- before the deadline, valid_to null or at or after it), not the as_of macro
-- the model uses. A fixture counts for a club on either side.
--
-- On the fixture tree the values are also pinned by hand, from stg_fixture and
-- stg_player directly: every 2026-27 GW3-4 row is 1. Player 4 departed after
-- the 2026-08-31 capture, so their realised fixture_count is 0 in both
-- gameweeks while club 1 still had a fixture scheduled (29 in GW3, 36 in
-- GW4): the one row on the tree where the column differs from fixture_count.
-- No status row closes on absence (dim_player_status_history), so GW4 still
-- reads club 1.

with gameweeks as (

    select season, gameweek, deadline_time
    from {{ ref('dim_gameweek') }} as gameweek
    where last_capture_before_deadline_at is not null
      and exists (
          select 1
          from {{ ref('dim_fixture_schedule_history') }} as schedule
          where schedule.season = gameweek.season
            and schedule.valid_from < gameweek.deadline_time
      )

),

club_at_deadline as (

    select
        player_gameweek.season,
        player_gameweek.fpl_id,
        player_gameweek.gameweek,
        status.team_fpl_id
    from {{ ref('fct_player_gameweek') }} as player_gameweek
    inner join gameweeks
        on gameweeks.season = player_gameweek.season
       and gameweeks.gameweek = player_gameweek.gameweek
    inner join {{ ref('dim_player_status_history') }} as status
        on status.season = player_gameweek.season
       and status.fpl_id = player_gameweek.fpl_id
       and status.valid_from < gameweeks.deadline_time
       and (status.valid_to is null or status.valid_to >= gameweeks.deadline_time)

),

schedule_at_deadline as (

    select gameweeks.season, gameweeks.gameweek, schedule.fixture_id,
        schedule.team_h_fpl_id, schedule.team_a_fpl_id
    from gameweeks
    inner join {{ ref('dim_fixture_schedule_history') }} as schedule
        on schedule.season = gameweeks.season
       and schedule.gameweek = gameweeks.gameweek
       and schedule.valid_from < gameweeks.deadline_time
       and (schedule.valid_to is null or schedule.valid_to >= gameweeks.deadline_time)

),

expected as (

    select
        club_at_deadline.season,
        club_at_deadline.fpl_id,
        club_at_deadline.gameweek,
        count(schedule_at_deadline.fixture_id) as expected_count
    from club_at_deadline
    left join schedule_at_deadline
        on schedule_at_deadline.season = club_at_deadline.season
       and schedule_at_deadline.gameweek = club_at_deadline.gameweek
       and club_at_deadline.team_fpl_id in (
           schedule_at_deadline.team_h_fpl_id, schedule_at_deadline.team_a_fpl_id)
    group by all

)

select player_gameweek.season, player_gameweek.fpl_id, player_gameweek.gameweek,
    expected.expected_count, player_gameweek.fixture_count_at_deadline,
    'differs from the as-of schedule count' as failure
from expected
inner join {{ ref('fct_player_gameweek') }} as player_gameweek
    on player_gameweek.season = expected.season
   and player_gameweek.fpl_id = expected.fpl_id
   and player_gameweek.gameweek = expected.gameweek
where player_gameweek.fixture_count_at_deadline is distinct from expected.expected_count

{% if target.name == 'fixtures' %}

union all

select pinned.season, pinned.fpl_id, pinned.gameweek,
    pinned.expected_count, player_gameweek.fixture_count_at_deadline,
    'differs from the hand-checked value' as failure
from (values
    ('2026-27', 4,   3, 1, 0), ('2026-27', 4,   4, 1, 0),
    ('2026-27', 166, 3, 1, 1), ('2026-27', 166, 4, 1, 1),
    ('2026-27', 233, 3, 1, 1), ('2026-27', 233, 4, 1, 1),
    ('2026-27', 426, 3, 1, 1), ('2026-27', 426, 4, 1, 1),
    ('2026-27', 427, 3, 1, 1), ('2026-27', 427, 4, 1, 1),
    ('2026-27', 611, 3, 1, 1), ('2026-27', 611, 4, 1, 1)
) as pinned (season, fpl_id, gameweek, expected_count, expected_fixture_count)
left join {{ ref('fct_player_gameweek') }} as player_gameweek
    on player_gameweek.season = pinned.season
   and player_gameweek.fpl_id = pinned.fpl_id
   and player_gameweek.gameweek = pinned.gameweek
where player_gameweek.fixture_count_at_deadline is distinct from pinned.expected_count
   or player_gameweek.fixture_count is distinct from pinned.expected_fixture_count

{% endif %}
