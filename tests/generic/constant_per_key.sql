-- constant_per_key: a column that must hold one non-null value per key,
-- declared in schema.yml.
--
--   data_tests:
--     - constant_per_key:
--         arguments: {key: [season, fpl_id]}
--         config: {tags: [unit]}
--
-- For a table with one row per capture, this asserts the value never changes
-- between captures and is never null in any of them. A key fails if any of
-- its rows is null or its rows hold more than one distinct value.
--
-- Returns one row per failing key: the key columns, the distinct non-null
-- values seen (distinct_values) and the number of null rows (null_rows), so a
-- failure names the key and what it held.
--
-- Written for stg_player.player_code (#69); #41's fixed-position rule is the
-- same shape. Singular tests generic_test_constant_per_key_* pin it.

{% test constant_per_key(model, column_name, key) %}

select
    {{ key | join(', ') }},
    string_agg(distinct cast({{ column_name }} as varchar), ', ')
        as distinct_values,
    count(*) filter (where {{ column_name }} is null) as null_rows
from {{ model }}
group by {{ key | join(', ') }}
having count(distinct {{ column_name }}) > 1
    or count(*) filter (where {{ column_name }} is null) > 0

{% endtest %}
