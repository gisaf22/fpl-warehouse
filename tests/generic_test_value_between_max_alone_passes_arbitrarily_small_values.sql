-- Layer: generic
-- Tests: value_between (tests/generic/value_between.sql)
-- Asserts: declared with a max alone, the lower side is unbounded — values on
--          or below the max pass however small.
-- Origin: new in #53, from the spec's edge case "only one bound given: the
--         other side is unbounded", which it lists under AC4
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#53 AC4'}) }}

{{ test_value_between(
    model="(select * from (values ('at_max', 5), ('large_negative', -1000000000)) as t(row_id, value))",
    column_name='value',
    max_value=5
) }}
