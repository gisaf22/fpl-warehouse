-- Layer: generic
-- Tests: value_between (tests/generic/value_between.sql)
-- Asserts: declared with a min alone, the upper side is unbounded — values on
--          or above the min pass however large, with no invented max.
-- Origin: new in #53
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#53 AC4'}) }}

{{ test_value_between(
    model="(select * from (values ('at_min', 0), ('large', 1000000000), ('bigint_max', 9223372036854775807)) as t(row_id, value))",
    column_name='value',
    min_value=0
) }}
