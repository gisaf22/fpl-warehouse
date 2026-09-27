-- Layer: generic
-- Tests: value_between (tests/generic/value_between.sql)
-- Asserts: a null value passes the range test; nullability is a separate
--          decision, tested by not_null where it applies.
-- Origin: new in #53
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#53 AC3'}) }}

{{ test_value_between(
    model="(select * from (values ('null_value', cast(null as integer)), ('inside', 3)) as t(row_id, value))",
    column_name='value',
    min_value=1,
    max_value=5
) }}
