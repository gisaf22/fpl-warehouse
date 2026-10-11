-- Layer: dim
-- Tests: dim_fixture_schedule_history
-- Asserts: within each (season, fixture_id) the rows' intervals neither
--          overlap nor leave a gap, and exactly one row is open, the last one.
-- Origin: new in #152, modelled on
--         tests/dim_test_player_status_history_intervals_contiguous_one_open.sql
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#152 AC7'}) }}

-- Each closed row's valid_to must equal the next row's valid_from; a smaller
-- one is a gap, a larger one an overlap. On the fixture tree, the 34
-- rescheduled fixtures each have two rows, so a closed row that is shifted
-- fails here.

with ordered as (

    select
        season,
        fixture_id,
        valid_from,
        valid_to,
        lead(valid_from) over fixture_rows as next_valid_from,
        count(*) filter (where valid_to is null) over (partition by season, fixture_id) as open_rows
    from {{ ref('dim_fixture_schedule_history') }}
    window fixture_rows as (
        partition by season, fixture_id
        order by valid_from, valid_to nulls last
    )

)

select season, fixture_id, valid_from, valid_to, next_valid_from, open_rows,
    case
        when open_rows <> 1                     then 'not exactly one open row'
        when valid_to is null                   then 'open row is not the last'
        when valid_to <= valid_from             then 'row closes at or before it opens'
        when valid_to < next_valid_from         then 'gap before the next row'
        else                                         'overlaps the next row'
    end as failure
from ordered
where open_rows <> 1
   or (valid_to is null and next_valid_from is not null)
   or valid_to <= valid_from
   or valid_to is distinct from next_valid_from and next_valid_from is not null
