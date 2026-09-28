-- STUB for #69, committed with the tests that pin it. Returns the real
-- test's columns and no rows, so it passes everything; replaced by the real
-- test in the implementation commit.

{% test constant_per_key(model, column_name, key) %}

select
    {{ key | join(', ') }},
    cast(null as varchar) as distinct_values,
    cast(null as bigint)  as null_rows
from {{ model }}
where false

{% endtest %}
