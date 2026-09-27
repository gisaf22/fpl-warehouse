-- Layer: generic
-- Tests: value_between (tests/generic/value_between.sql)
-- Asserts: declared with a min alone, a value below the min still fails —
--          the one-sided declaration enforces the side it names.
-- Origin: new in #53
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#53 AC4'}) }}

-- Without this, an implementation that ignored a lone min would pass
-- generic_test_value_between_min_alone_passes_arbitrarily_large_values by
-- never failing anything.

with failing as (

    {{ test_value_between(
        model="(select * from (values ('below_min', -1), ('at_min', 0), ('large', 1000000000)) as t(row_id, value))",
        column_name='value',
        min_value=0
    ) }}

),

expected as (

    select * from (values ('below_min')) as e(row_id)

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
