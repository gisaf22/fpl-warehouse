-- Layer: fct
-- Tests: fct_player_market_snapshot
-- Asserts: every stored market value equals stg_player's for the same
--          (season, fpl_id, capture_key), and the table has exactly the
--          key, capture and source columns: no derived column exists.
-- Origin: new in #141
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#141 AC4'}) }}

-- stg_player's values equal the source as published (#140 AC1, AC2), so
-- equality with it is equality with the source. The column list is read from
-- the built table, so a derived column added to the model fails here.

with expected_columns (column_name) as (
    values ('season'), ('fpl_id'), ('capture_key'), ('observed_at'),
           ('now_cost'), ('selected_by_percent'), ('transfers_in_event'),
           ('transfers_out_event'), ('total_players')
),

actual_columns as (
    select column_name
    from information_schema.columns
    where table_schema = '{{ ref("fct_player_market_snapshot").schema }}'
      and table_name = '{{ ref("fct_player_market_snapshot").identifier }}'
)

select
    snapshot.capture_key,
    snapshot.fpl_id,
    'value differs from stg_player' as problem
from {{ ref('fct_player_market_snapshot') }} as snapshot
inner join {{ ref('stg_player') }} as staged
    on  staged.season = snapshot.season
    and staged.fpl_id = snapshot.fpl_id
    and staged.capture_key = snapshot.capture_key
where staged.now_cost            is distinct from snapshot.now_cost
   or staged.selected_by_percent is distinct from snapshot.selected_by_percent
   or staged.transfers_in_event  is distinct from snapshot.transfers_in_event
   or staged.transfers_out_event is distinct from snapshot.transfers_out_event
   or staged.total_players       is distinct from snapshot.total_players

union all

(select null, null, 'column not a key, capture or source column: ' || column_name
 from (select column_name from actual_columns except select column_name from expected_columns))

union all

(select null, null, 'expected column missing: ' || column_name
 from (select column_name from expected_columns except select column_name from actual_columns))
