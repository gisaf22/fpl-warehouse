-- Layer: dim
-- Tests: dim_player_status_history
-- Asserts: within each (season, fpl_id) the rows' intervals neither overlap
--          nor leave a gap, and exactly one row is open, the last one.
-- Origin: new in #126
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#126 AC5'}) }}

-- Rows are ordered by valid_from, then valid_to with the open row last: a
-- same-instant tie between two captures gives a zero-length row, which must
-- still close where the next one opens. Each closed row's valid_to must equal
-- the next row's valid_from; a smaller one is a gap, a larger one an overlap.

with ordered as (

    select
        season,
        fpl_id,
        valid_from,
        valid_to,
        lead(valid_from) over player_rows as next_valid_from,
        count(*) filter (where valid_to is null) over (partition by season, fpl_id) as open_rows
    from {{ ref('dim_player_status_history') }}
    window player_rows as (
        partition by season, fpl_id
        order by valid_from, valid_to nulls last
    )

)

select season, fpl_id, valid_from, valid_to, next_valid_from, open_rows,
    case
        when open_rows <> 1                     then 'not exactly one open row'
        when valid_to is null                   then 'open row is not the last'
        when valid_to < valid_from              then 'row closes before it opens'
        when valid_to < next_valid_from         then 'gap before the next row'
        else                                         'overlaps the next row'
    end as failure
from ordered
where open_rows <> 1
   or (valid_to is null and next_valid_from is not null)
   or valid_to < valid_from
   or valid_to is distinct from next_valid_from and next_valid_from is not null
