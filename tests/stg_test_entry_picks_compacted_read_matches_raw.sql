-- Layer: stg
-- Tests: stg_entry_picks_capture
-- Asserts: staging's read of entry-picks (compacted gameweeks from parquet,
--          the rest from raw) holds exactly the admitted captures an all-raw
--          read holds, with the same payload values; the fixture has a
--          compacted gameweek, so both halves are read.
-- Origin: new in #216 (D8)
-- Tier: integration
-- Fixture tree only, as stg_test_player_fixture_matches_direct_read: on a
-- live target it would re-read every raw payload.
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC16'},
          enabled=(target.name == 'fixtures')) }}

with raw_read as (

    select
        {{ capture_key_from_filename() }} as capture_key,
        cast(entry_history.points as integer) as points,
        len(picks)                            as pick_count
    from {{ entry_picks_raw_read() }}

),

admitted_raw as (

    select raw_read.*
    from raw_read
    inner join {{ ref('int_admitted_capture') }} using (capture_key)

),

staged as (

    select capture_key, points, pick_count
    from {{ ref('stg_entry_picks_capture') }}

)

(select 'raw only' as side, * from admitted_raw except all select 'raw only', * from staged)
union all
(select 'staged only', * from staged except all select 'staged only', * from admitted_raw)
union all
select 'no compacted gameweek in the fixture', null, null, null
where not exists (
    select 1 from glob('tests/fixtures/compacted/fpl/entry-picks/_manifest/*/*.json')
)
