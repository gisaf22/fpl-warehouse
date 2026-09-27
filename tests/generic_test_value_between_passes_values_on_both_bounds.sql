-- Layer: generic
-- Tests: value_between (tests/generic/value_between.sql)
-- Asserts: a value equal to min or to max is in range — the bounds are
--          inclusive, so a column holding only in-range values passes.
-- Origin: new in #53
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#53 AC1'}) }}

-- Runs the generic test's own SQL against an inline relation. It returns the
-- rows it considers failing, so any row here fails this test.

{{ test_value_between(
    model="(select * from (values ('at_min', 1), ('inside', 3), ('at_max', 5)) as t(row_id, value))",
    column_name='value',
    min_value=1,
    max_value=5
) }}
