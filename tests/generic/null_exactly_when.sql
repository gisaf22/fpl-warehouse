-- null_exactly_when: columns that are NULL on exactly the rows matching a
-- condition, declared once per model in schema.yml.
--
--   data_tests:
--     - null_exactly_when:
--         arguments:
--           condition: "fixture_count = 0"
--           columns: [minutes, starts, ...]
--         config: {tags: [integration]}
--
-- A row fails when the condition holds and a listed column is not NULL, or
-- when it does not hold and a listed column is NULL. A NULL condition counts
-- as not holding, so a row the condition cannot judge fails rather than
-- passes. An empty column list fails compilation: it would pass every row.
--
-- Returns the offending rows whole, plus violating_columns naming each listed
-- column that broke the rule on that row.
--
-- Written for fct_player_gameweek's 27 measures (#186, #133 S17): NULL where
-- nothing was observed, real values (zeros included) wherever a fixture was.

{% test null_exactly_when(model, condition, columns) %}

{% if not columns %}
    {{ exceptions.raise_compiler_error(
        "null_exactly_when on " ~ model ~ " needs at least one column"
    ) }}
{% endif %}

with judged as (

    select
        *,
        coalesce(({{ condition }}), false) as condition_holds
    from {{ model }}

),

violations as (

    select
        *,
        concat_ws(', '
        {%- for column in columns %},
            case when condition_holds <> ({{ column }} is null)
                then '{{ column }}' end
        {%- endfor %}
        ) as violating_columns
    from judged

)

select *
from violations
where violating_columns <> ''

{% endtest %}
