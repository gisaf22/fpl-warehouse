-- Layer: generic
-- Tests: value_between (tests/generic/value_between.sql)
-- Asserts: a value below min or above max fails, and the failure returns
--          exactly the offending rows, whole, so they can be identified.
-- Origin: new in #53
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#53 AC2'}) }}

-- The generic test returns its failing rows. They are compared by row_id
-- against the rows that are genuinely out of range: a missing one means an
-- out-of-range value passed, an extra one means an in-range value failed, and
-- a failing row without its row_id does not identify the row and cannot join.

with failing as (

    {{ test_value_between(
        model="(select * from (values ('below_min', 0), ('at_min', 1), ('inside', 3), ('at_max', 5), ('above_max', 6)) as t(row_id, value))",
        column_name='value',
        min_value=1,
        max_value=5
    ) }}

),

expected as (

    select * from (values ('below_min'), ('above_max')) as e(row_id)

)

select
    coalesce(failing.row_id, expected.row_id) as row_id,
    failing.row_id is not null                as reported_failing,
    expected.row_id is not null               as is_out_of_range
from failing
full outer join expected
    on failing.row_id = expected.row_id
where failing.row_id is null
   or expected.row_id is null
