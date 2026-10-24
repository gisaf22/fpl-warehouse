-- Layer: stg
-- Tests: stg_entry_picks_capture
-- Asserts: overall_rank is raw entry_history.overall_rank as it is, 0 kept as
--          0 and null as null, from compacted gameweeks and the raw tail alike.
-- Origin: new in #219 (D1). In the fixture, 1276382 reads 7,960,655 in GW1
--         and 0 in GW3 (both compacted), 0 in GW2 and null in GW4 (raw tail).
-- Tier: integration
-- Fixture tree only, as stg_test_entry_picks_compacted_read_matches_raw: on a
-- live target it would re-read every raw payload.
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#219 AC1'},
          enabled=(target.name == 'fixtures')) }}

with raw_read as (

    select
        {{ capture_key_from_filename() }}            as capture_key,
        cast(entry_history.overall_rank as bigint)   as overall_rank
    from {{ entry_picks_raw_read() }}

),

admitted_raw as (

    select raw_read.*
    from raw_read
    inner join {{ ref('int_admitted_capture') }} using (capture_key)

),

staged as (

    select capture_key, cast(overall_rank as bigint) as overall_rank
    from {{ ref('stg_entry_picks_capture') }}

)

-- except all treats two nulls as equal, so a null turned into 0 is a difference.
(select 'raw only' as side, * from admitted_raw except all select 'raw only', * from staged)
union all
(select 'staged only', * from staged except all select 'staged only', * from admitted_raw)
union all
select 'no staged 0 and null in the fixture', null, null
where not exists (select 1 from {{ ref('stg_entry_picks_capture') }} where overall_rank = 0)
   or not exists (select 1 from {{ ref('stg_entry_picks_capture') }} where overall_rank is null)
