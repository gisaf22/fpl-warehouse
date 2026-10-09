-- Layer: stg
-- Tests: stg_player
-- Asserts: within a season, every player in a bootstrap-static capture is in
--          the next one. Player status history never closes a row on absence
--          (that rule was rejected on #123), so a player who drops out keeps
--          an open row; this names them.
-- Origin: new in #126
-- Tier: integration. Warn severity: the build passes and the warning names
--       each fpl_id and the two captures.
{{ config(group='warehouse_internal', tags=['integration'], severity='warn', meta={'covers': '#126 AC8'}) }}

-- Captures are ordered by observed_at, then run_id, as everywhere else. The
-- fixture tree warns here by construction: its player 4 departs on purpose
-- (stg_test_player_departure_present).

with captures as (

    select
        season,
        capture_key,
        lead(capture_key) over (
            partition by season
            order by observed_at, run_id
        ) as next_capture_key
    from (select distinct season, capture_key, observed_at, run_id from {{ ref('stg_player') }})

)

select
    captures.season,
    player.fpl_id,
    captures.capture_key      as last_seen_in,
    captures.next_capture_key as missing_from,
    'player absent from the next capture' as warning
from captures
inner join {{ ref('stg_player') }} as player
    on  player.season = captures.season
    and player.capture_key = captures.capture_key
where captures.next_capture_key is not null
  and not exists (
      select 1
      from {{ ref('stg_player') }} as next_player
      where next_player.season = captures.season
        and next_player.capture_key = captures.next_capture_key
        and next_player.fpl_id = player.fpl_id
  )
