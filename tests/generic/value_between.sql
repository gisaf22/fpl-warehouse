-- value_between: a numeric column's valid range, declared in schema.yml.
--
--   data_tests:
--     - value_between:
--         arguments: {min_value: 1, max_value: 5}
--         config: {tags: [unit]}
--
-- Both bounds are inclusive, and either may be left out to leave that side
-- unbounded (scores have a floor of 0 and no meaningful ceiling). At least one
-- is required: a declaration with neither would pass every row.
--
-- Null values pass. Nullability is a separate decision, tested by not_null
-- where it applies, so a range test must not quietly become a not-null test.
--
-- Returns the offending rows whole, so a failure identifies them.
-- Singular tests generic_test_value_between_* pin each of these behaviours
-- (#53).

{% test value_between(model, column_name, min_value=none, max_value=none) %}

{% if min_value is none and max_value is none %}
    {{ exceptions.raise_compiler_error(
        "value_between on " ~ column_name ~ " needs min_value, max_value or both"
    ) }}
{% endif %}

select *
from {{ model }}
where {{ column_name }} is not null
  and (
      {%- if min_value is not none %}
      {{ column_name }} < {{ min_value }}
      {%- endif %}
      {%- if min_value is not none and max_value is not none %} or{% endif %}
      {%- if max_value is not none %}
      {{ column_name }} > {{ max_value }}
      {%- endif %}
  )

{% endtest %}
